//! RTD physical placement, rail, decoupling, locality, and noise checks.

mod donor_geometry;
mod ipc;

use zapote_core::{CheckReport, Finding, Pad, RunInput};

pub fn validate(input: &RunInput) -> CheckReport {
    let mut findings = Vec::new();
    let mut gaps = Vec::new();
    let mut checked = Vec::new();
    let schema_errors = input.validate();
    if !schema_errors.is_empty() {
        for error in schema_errors {
            findings.push(Finding::indeterminate("INPUT_SCHEMA", error, "run_input"));
        }
        return CheckReport::from_findings(findings, checked, gaps);
    }
    check_rail(input, &mut findings, &mut checked);
    check_decoupling(input, &mut findings, &mut gaps, &mut checked);
    check_sensitive_geometry(input, &mut findings, &mut gaps, &mut checked);
    check_prohibited_connections(input, &mut findings, &mut gaps, &mut checked);
    check_native_geometry(input, &mut findings, &mut gaps, &mut checked);
    check_local_escape_eligibility(input, &mut findings, &mut gaps, &mut checked);
    CheckReport::from_findings(findings, checked, gaps)
}

fn check_local_escape_eligibility(
    input: &RunInput,
    findings: &mut Vec<Finding>,
    gaps: &mut Vec<String>,
    checked: &mut Vec<String>,
) {
    const RULE: &str = "DRC.RTD.LOCAL_ESCAPE_ELIGIBILITY";
    checked.push(RULE.into());
    if input.board.paths.is_empty() {
        gaps.push("no authored local-escape membership groups were supplied; escape eligibility is indeterminate".into());
        findings.push(Finding::indeterminate(
            RULE,
            "authored local-escape membership population is empty",
            "paths",
        ));
        return;
    }

    let qualified: std::collections::BTreeSet<_> = input
        .rtd
        .required_local_ics
        .iter()
        .map(|ic| ic.component.as_str())
        .chain(
            input
                .rtd
                .decoupling
                .iter()
                .map(|cap| cap.component.as_str()),
        )
        .collect();
    let net_domains: std::collections::BTreeMap<_, _> = input
        .board
        .nets
        .iter()
        .map(|net| (net.name.as_str(), net.domain.as_str()))
        .collect();

    for group in &input.board.paths {
        let object = group.name.clone();
        let mut errors = Vec::new();
        let terminal_pad_ids: &[String] = if group.terminal_pad_ids.is_empty() {
            &group.pad_ids
        } else {
            &group.terminal_pad_ids
        };
        let clearance_pad_ids = &group.clearance_pad_ids;
        if group.name.trim().is_empty() {
            errors.push("group name is empty".to_string());
        }
        if group.nets.is_empty() {
            errors.push("group has no nets".to_string());
        }
        for net in &group.nets {
            match net_domains.get(net.as_str()) {
                Some(domain) if *domain == "SELV_LV" => {}
                Some(domain) => errors.push(format!("net {net} has non-SELV domain {domain}")),
                None => errors.push(format!("net {net} is absent from the board net census")),
            }
        }
        if group.component_ids.is_empty()
            || group
                .component_ids
                .iter()
                .any(|component| !qualified.contains(component.as_str()))
        {
            errors.push("group contains an unqualified IC/bypass component".to_string());
        }
        if group.uses_buck_or_mcu_trunk {
            errors.push("buck or MCU trunk membership is forbidden".to_string());
        }
        if group.uses_shared_spine {
            errors.push("shared-spine membership is forbidden".to_string());
        }

        let current = match group.max_branch_current_a {
            Some(value) if value.is_finite() && value > 0.0 => value,
            _ => {
                errors.push("maximum branch current must be a finite positive bound".to_string());
                0.0
            }
        };
        let thickness = match group.copper_thickness_um {
            Some(value) if value.is_finite() && value >= 70.0 => value,
            Some(value) if value.is_finite() => {
                errors.push(format!(
                    "finished copper thickness {value:.3} um is below 70 um"
                ));
                value
            }
            _ => {
                errors.push(
                    "finished copper thickness must be a finite bound of at least 70 um"
                        .to_string(),
                );
                0.0
            }
        };
        let max_route = match group.max_route_mm {
            Some(value) if value.is_finite() && value >= 0.0 && value <= 3.0 => value,
            Some(value) => {
                errors.push(format!(
                    "connected route allowance {value:.3} mm must be within 0..=3 mm"
                ));
                value
            }
            None => {
                errors.push("connected route allowance is required".to_string());
                0.0
            }
        };

        let mut route_length = 0.0;
        let mut seen_traces = std::collections::BTreeSet::new();
        if group.trace_ids.is_empty() {
            errors.push("group has no explicit trace membership".to_string());
        }
        for trace_id in &group.trace_ids {
            if !seen_traces.insert(trace_id) {
                errors.push(format!("trace {trace_id} is listed more than once"));
                continue;
            }
            let trace = input
                .board
                .traces
                .iter()
                .find(|trace| trace.id == *trace_id);
            let Some(trace) = trace else {
                errors.push(format!(
                    "trace {trace_id} is absent from the native trace census"
                ));
                continue;
            };
            if trace.layer != "F.Cu" && trace.layer != "B.Cu" {
                errors.push(format!(
                    "trace {trace_id} uses non-outer layer {}",
                    trace.layer
                ));
            }
            if trace.width_mm < 0.25 {
                errors.push(format!(
                    "trace {trace_id} is only {:.3} mm; 0.25 mm is required",
                    trace.width_mm
                ));
            }
            if !group.nets.iter().any(|net| net == &trace.net) {
                errors.push(format!(
                    "trace {trace_id} net {} is outside group nets",
                    trace.net
                ));
            }
            route_length += trace
                .points_mm
                .windows(2)
                .map(|segment| {
                    let dx = segment[1][0] - segment[0][0];
                    let dy = segment[1][1] - segment[0][1];
                    (dx * dx + dy * dy).sqrt()
                })
                .sum::<f64>();
            if thickness >= 70.0
                && current > 0.0
                && ipc::external_capacity_a(trace.width_mm, thickness) < current
            {
                errors.push(format!(
                    "trace {trace_id} IPC capacity {:.3} A is below {:.3} A branch bound",
                    ipc::external_capacity_a(trace.width_mm, thickness),
                    current
                ));
            }
        }
        if !group.trace_ids.is_empty() && route_length > max_route {
            errors.push(format!(
                "connected route is {:.3} mm, above {:.3} mm allowance",
                route_length, max_route
            ));
        }

        let mut seen_vias = std::collections::BTreeSet::new();
        for via_id in &group.via_ids {
            if !seen_vias.insert(via_id) {
                errors.push(format!("via {via_id} is listed more than once"));
                continue;
            }
            if !input.board.vias.iter().any(|via| via.id == *via_id) {
                errors.push(format!("via {via_id} is absent from the native via census"));
            } else if let Some(via) = input.board.vias.iter().find(|via| via.id == *via_id) {
                if !group.nets.iter().any(|net| net == &via.net) {
                    errors.push(format!(
                        "via {via_id} net {} is outside group nets",
                        via.net
                    ));
                }
            }
        }

        if terminal_pad_ids.is_empty() {
            errors.push("group needs an explicit load-side terminal pad".to_string());
        }
        if group.junction_pad_ids.is_empty() {
            errors.push("group needs an explicit native trunk/pour junction pad".to_string());
        } else {
            let mut pads = Vec::new();
            let mut seen_pads = std::collections::BTreeSet::new();
            for pad_id in terminal_pad_ids {
                if !seen_pads.insert(pad_id) {
                    errors.push(format!("pad {pad_id} is listed more than once"));
                }
                let Some((component_id, pad_number)) = pad_id.rsplit_once('.') else {
                    errors.push(format!("pad membership {pad_id} is not component.pad"));
                    continue;
                };
                let Some(component) = input.board.components.iter().find(|c| c.id == component_id)
                else {
                    errors.push(format!("pad membership {pad_id} names an absent component"));
                    continue;
                };
                let Some(pad) = component
                    .footprint_pads
                    .iter()
                    .find(|pad| pad.pad == pad_number)
                else {
                    errors.push(format!(
                        "pad membership {pad_id} is absent from footprint pad census"
                    ));
                    continue;
                };
                if !group.nets.iter().any(|net| net == &pad.net) {
                    errors.push(format!(
                        "pad {pad_id} net {} is outside group nets",
                        pad.net
                    ));
                }
                if net_domains.get(pad.net.as_str()) != Some(&"SELV_LV") {
                    errors.push(format!("pad {pad_id} is not on a SELV_LV net"));
                }
                if !group
                    .component_ids
                    .iter()
                    .any(|component| component == component_id)
                {
                    errors.push(format!(
                        "pad {pad_id} belongs to a component outside group membership"
                    ));
                }
                pads.push((component_id, pad));
            }
            if !clearance_pad_ids.is_empty() {
                let mut clearance_pads = Vec::new();
                for pad_id in clearance_pad_ids {
                    let Some((component_id, pad_number)) = pad_id.rsplit_once('.') else {
                        errors.push(format!("clearance pad {pad_id} is not component.pad"));
                        continue;
                    };
                    let Some(component) =
                        input.board.components.iter().find(|c| c.id == component_id)
                    else {
                        errors.push(format!("clearance pad {pad_id} names an absent component"));
                        continue;
                    };
                    let Some(pad) = component
                        .footprint_pads
                        .iter()
                        .find(|pad| pad.pad == pad_number)
                    else {
                        errors.push(format!(
                            "clearance pad {pad_id} is absent from footprint pad census"
                        ));
                        continue;
                    };
                    clearance_pads.push((component_id, pad));
                }
                if clearance_pads.len() < 2 {
                    errors.push("clearance qualification needs at least two pads".to_string());
                } else if clearance_pads
                    .iter()
                    .any(|(component, _)| *component != clearance_pads[0].0)
                {
                    errors.push(
                        "clearance pad population must stay within one IC footprint".to_string(),
                    );
                }
                for (index, (_, first)) in clearance_pads.iter().enumerate() {
                    for (_, second) in clearance_pads.iter().skip(index + 1) {
                        if pad_clearance_mm(first, second) < 0.20 {
                            errors.push(format!(
                                "same-IC pad copper boundaries are below the 0.20 mm spacing floor ({:.3} mm)",
                                pad_clearance_mm(first, second)
                            ));
                        }
                    }
                }
            }
            // A selected trace is eligible only when every endpoint is tied to
            // the explicitly selected pad/via population or to another segment
            // of the same net. This rejects an arbitrary short fragment that
            // happens to satisfy width/ampacity/length on its own.
            let selected_pads = pads.iter().map(|(_, pad)| *pad).collect::<Vec<_>>();
            let selected_vias = group
                .via_ids
                .iter()
                .filter_map(|via_id| input.board.vias.iter().find(|via| via.id == *via_id))
                .collect::<Vec<_>>();

            // Corroborate the authored negative claims against native copper
            // clusters. Exact source instance identities are used here; no
            // substring or net-name inference is allowed. A local pad that
            // shares its native cluster with a switching, buck, or MCU trunk
            // is never eligible even if a mutable JSON flag says otherwise.
            const FORBIDDEN_TRUNK_COMPONENTS: [&str; 5] = [
                "mcu.mcu",
                "power_mgmt.buck_3v3.buck",
                "power_mgmt.buck_3v3.l_out",
                "hb.power_loop.q_high",
                "hb.power_loop.q_low",
            ];
            let junction_ids = group
                .junction_pad_ids
                .iter()
                .collect::<std::collections::BTreeSet<_>>();
            for pad_id in terminal_pad_ids {
                let Some((component_id, pad_number)) = pad_id.rsplit_once('.') else {
                    continue;
                };
                let Some(component) = input.board.components.iter().find(|c| c.id == component_id)
                else {
                    continue;
                };
                let Some(pad) = component
                    .footprint_pads
                    .iter()
                    .find(|pad| pad.pad == pad_number)
                else {
                    continue;
                };
                for cluster in input.board.connectivity_clusters.iter().filter(|cluster| {
                    cluster.net == pad.net && cluster.nodes.iter().any(|node| node == pad_id)
                }) {
                    for forbidden in FORBIDDEN_TRUNK_COMPONENTS {
                        if cluster.nodes.iter().any(|node| {
                            (node == forbidden || node.starts_with(&format!("{forbidden}.")))
                                && !junction_ids.iter().any(|junction| {
                                    node == *junction || node.starts_with(&format!("{junction}."))
                                })
                        }) {
                            errors.push(format!(
                                "pad {pad_id} shares native copper cluster with forbidden trunk {forbidden}"
                            ));
                        }
                    }
                }
            }
            let junction_pads = group
                .junction_pad_ids
                .iter()
                .filter_map(|pad_id| {
                    let Some((component_id, pad_number)) = pad_id.rsplit_once('.') else {
                        errors.push(format!("junction pad {pad_id} is not component.pad"));
                        return None;
                    };
                    let Some(component) =
                        input.board.components.iter().find(|c| c.id == component_id)
                    else {
                        errors.push(format!("junction pad {pad_id} names an absent component"));
                        return None;
                    };
                    let Some(pad) = component
                        .footprint_pads
                        .iter()
                        .find(|pad| pad.pad == pad_number)
                    else {
                        errors.push(format!(
                            "junction pad {pad_id} is absent from footprint pad census"
                        ));
                        return None;
                    };
                    if !group.nets.iter().any(|net| net == &pad.net) {
                        errors.push(format!(
                            "junction pad {pad_id} net {} is outside group nets",
                            pad.net
                        ));
                    }
                    Some(pad)
                })
                .collect::<Vec<_>>();
            let mut anchor_pads = selected_pads.clone();
            anchor_pads.extend(junction_pads);
            for trace_id in &group.trace_ids {
                let Some(trace) = input
                    .board
                    .traces
                    .iter()
                    .find(|trace| trace.id == *trace_id)
                else {
                    continue;
                };
                for endpoint in [trace.points_mm.first(), trace.points_mm.last()]
                    .into_iter()
                    .flatten()
                {
                    let anchored = anchor_pads.iter().any(|pad| {
                        pad.net == trace.net && point_near_pad(*endpoint, trace.layer.as_str(), pad)
                    }) || selected_vias.iter().any(|via| {
                        via.net == trace.net
                            && distance_mm(*endpoint, via.position_mm) <= via.drill_mm / 2.0 + 0.10
                    });
                    let joined = group.trace_ids.iter().any(|other_id| {
                        let Some(other) = input
                            .board
                            .traces
                            .iter()
                            .find(|other| other.id == *other_id)
                        else {
                            return false;
                        };
                        other.id != trace.id
                            && other.net == trace.net
                            && [other.points_mm.first(), other.points_mm.last()]
                                .into_iter()
                                .flatten()
                                .any(|other_endpoint| {
                                    distance_mm(*endpoint, *other_endpoint) <= 0.001
                                })
                    });
                    if !anchored && !joined {
                        errors.push(format!(
                            "trace {trace_id} endpoint [{:.3},{:.3}] is disconnected from selected pads/vias and same-net segments",
                            endpoint[0], endpoint[1]
                        ));
                    }
                }
            }
            let selected_traces = group
                .trace_ids
                .iter()
                .filter_map(|trace_id| {
                    input
                        .board
                        .traces
                        .iter()
                        .find(|trace| trace.id == *trace_id)
                })
                .collect::<Vec<_>>();
            if !trace_components_have_anchors(&selected_traces, &anchor_pads, &selected_vias) {
                errors.push(
                    "selected trace membership contains a closed or disconnected component with no physical terminal anchor"
                        .to_string(),
                );
            }
        }

        if errors.is_empty() {
            findings.push(Finding::pass(
                RULE,
                format!("{object} admitted: explicit SELV pad/trace membership satisfies local escape bounds"),
                object,
            ));
        } else {
            findings.push(Finding::fail(RULE, errors.join("; "), object));
        }
    }
}

fn distance_mm(first: [f64; 2], second: [f64; 2]) -> f64 {
    let dx = first[0] - second[0];
    let dy = first[1] - second[1];
    (dx * dx + dy * dy).sqrt()
}

fn minimum_pad_distance(first: &[&Pad], second: &[&Pad]) -> f64 {
    first
        .iter()
        .flat_map(|a| {
            second
                .iter()
                .map(move |b| distance_mm(a.position_mm, b.position_mm))
        })
        .fold(f64::INFINITY, f64::min)
}

fn pad_half_extents_mm(pad: &Pad) -> [f64; 2] {
    let theta = pad.orientation_deg.to_radians();
    let (sin, cos) = theta.sin_cos();
    [
        (pad.size_mm[0] * cos.abs() + pad.size_mm[1] * sin.abs()) / 2.0,
        (pad.size_mm[0] * sin.abs() + pad.size_mm[1] * cos.abs()) / 2.0,
    ]
}

fn pad_clearance_mm(first: &Pad, second: &Pad) -> f64 {
    let first_half = pad_half_extents_mm(first);
    let second_half = pad_half_extents_mm(second);
    let dx = (first.position_mm[0] - second.position_mm[0]).abs() - first_half[0] - second_half[0];
    let dy = (first.position_mm[1] - second.position_mm[1]).abs() - first_half[1] - second_half[1];
    if dx >= 0.0 && dy >= 0.0 {
        (dx * dx + dy * dy).sqrt()
    } else {
        dx.max(dy)
    }
}

fn point_near_pad(point: [f64; 2], layer: &str, pad: &Pad) -> bool {
    let half = pad_half_extents_mm(pad);
    pad.layers.iter().any(|pad_layer| pad_layer == layer)
        && (point[0] - pad.position_mm[0]).abs() <= half[0] + 0.10
        && (point[1] - pad.position_mm[1]).abs() <= half[1] + 0.10
}

fn trace_components_have_anchors(
    traces: &[&zapote_core::Trace],
    pads: &[&Pad],
    vias: &[&zapote_core::Via],
) -> bool {
    if traces.is_empty() {
        return false;
    }
    let mut remaining = (0..traces.len()).collect::<std::collections::BTreeSet<_>>();
    while let Some(&seed) = remaining.iter().next() {
        remaining.remove(&seed);
        let mut component = vec![seed];
        let mut cursor = 0;
        while cursor < component.len() {
            let current = component[cursor];
            let joined = remaining
                .iter()
                .copied()
                .filter(|candidate| traces_join(traces[current], traces[*candidate]))
                .collect::<Vec<_>>();
            for candidate in joined {
                remaining.remove(&candidate);
                component.push(candidate);
            }
            cursor += 1;
        }
        let anchored = component.iter().any(|index| {
            let trace = traces[*index];
            [trace.points_mm.first(), trace.points_mm.last()]
                .into_iter()
                .flatten()
                .any(|point| {
                    pads.iter().any(|pad| {
                        pad.net == trace.net && point_near_pad(*point, trace.layer.as_str(), pad)
                    }) || vias.iter().any(|via| {
                        via.net == trace.net
                            && distance_mm(*point, via.position_mm) <= via.drill_mm / 2.0 + 0.10
                    })
                })
        });
        if !anchored {
            return false;
        }
    }
    true
}

fn traces_join(first: &zapote_core::Trace, second: &zapote_core::Trace) -> bool {
    first.net == second.net
        && first.layer == second.layer
        && [first.points_mm.first(), first.points_mm.last()]
            .into_iter()
            .flatten()
            .any(|a| {
                [second.points_mm.first(), second.points_mm.last()]
                    .into_iter()
                    .flatten()
                    .any(|b| distance_mm(*a, *b) <= 0.001)
            })
}

fn check_rail(input: &RunInput, findings: &mut Vec<Finding>, checked: &mut Vec<String>) {
    checked.push("DRC.RTD.UPSTREAM_POST_FERRITE_RAILS".into());
    checked.push("DRC.RTD.FERRITE_SEMANTICS".into());
    let rail = &input.rtd.local_rail;
    let has_upstream = input
        .board
        .connections
        .iter()
        .any(|c| c.component == rail.ferrite_component && c.net == rail.upstream_net);
    let has_post = input
        .board
        .connections
        .iter()
        .any(|c| c.component == rail.ferrite_component && c.net == rail.post_ferrite_net);
    if !has_upstream || !has_post {
        findings.push(Finding::fail(
            "DRC.RTD.UPSTREAM_POST_FERRITE_RAILS",
            format!(
                "ferrite {} must have explicit {} -> {} source connections",
                rail.ferrite_component, rail.upstream_net, rail.post_ferrite_net
            ),
            rail.ferrite_component.clone(),
        ));
    }
    if rail.upstream_net == rail.post_ferrite_net {
        findings.push(Finding::fail(
            "DRC.RTD.UPSTREAM_POST_FERRITE_RAILS",
            "upstream and post-ferrite nets must be distinct identities",
            rail.ferrite_component.clone(),
        ));
    }
    if let Some(ferrite) = input
        .board
        .components
        .iter()
        .find(|c| c.id == rail.ferrite_component)
    {
        if ferrite.kind.to_ascii_lowercase().contains("resistor") {
            findings.push(Finding::fail("DRC.RTD.FERRITE_SEMANTICS", "ferrite bead is represented as a resistor kind; preserve its impedance/model identity separately from DC resistance", ferrite.id.clone()));
        }
    }
}

fn check_decoupling(
    input: &RunInput,
    findings: &mut Vec<Finding>,
    gaps: &mut Vec<String>,
    checked: &mut Vec<String>,
) {
    checked.push("DRC.RTD.LOCAL_DECOUPLING".into());
    for required_ic in &input.rtd.required_local_ics {
        let ic = required_ic.component.as_str();
        let rail = required_ic.rail.as_str();
        let caps: Vec<_> = input.rtd.decoupling.iter().filter(|d| d.ic == ic).collect();
        if caps.is_empty() {
            findings.push(Finding::fail(
                "DRC.RTD.LOCAL_DECOUPLING",
                format!("{ic} has no local bypass entry"),
                ic.to_string(),
            ));
            continue;
        }
        let supply_caps: Vec<_> = caps
            .iter()
            .filter(|d| d.rail == rail && d.ground == required_ic.ground && d.capacitance_uf > 0.0)
            .copied()
            .collect();
        if supply_caps.is_empty() {
            findings.push(Finding::fail(
                "DRC.RTD.LOCAL_DECOUPLING",
                format!(
                    "{ic} bypass must connect {rail} to {} with positive capacitance",
                    required_ic.ground
                ),
                ic.to_string(),
            ));
        }
        if let Some(component) = input.board.components.iter().find(|c| c.id == ic) {
            let cap = supply_caps.iter().min_by(|a, b| {
                distance(a.position_mm, component.position_mm.as_slice())
                    .partial_cmp(&distance(b.position_mm, component.position_mm.as_slice()))
                    .unwrap_or(std::cmp::Ordering::Equal)
            });
            if let Some(cap) = cap {
                let cap_component = input
                    .board
                    .components
                    .iter()
                    .find(|component| component.id == cap.component);
                if match cap_component {
                    None => true,
                    Some(component) => {
                        let kind = component.kind.to_ascii_lowercase();
                        !(kind.contains("capac")
                            || kind.starts_with("c_")
                            || kind.starts_with("c-"))
                    }
                } {
                    findings.push(Finding::fail(
                        "DRC.RTD.LOCAL_DECOUPLING",
                        format!("{} is not a board capacitor bound to {ic}", cap.component),
                        cap.component.clone(),
                    ));
                }
                let actual_nets: std::collections::BTreeSet<_> = input
                    .board
                    .connections
                    .iter()
                    .filter(|connection| connection.component == cap.component)
                    .map(|connection| connection.net.as_str())
                    .collect();
                if !actual_nets.contains(rail)
                    || !actual_nets.contains(&required_ic.ground.as_str())
                {
                    findings.push(Finding::fail(
                        "DRC.RTD.LOCAL_DECOUPLING",
                        format!(
                            "board capacitor {} is not connected to {rail} and {}",
                            cap.component, required_ic.ground
                        ),
                        cap.component.clone(),
                    ));
                }
                let pad_locality = cap_component.and_then(|actual_cap| {
                    let ic_rail_pads = component
                        .footprint_pads
                        .iter()
                        .filter(|pad| pad.net == rail)
                        .collect::<Vec<_>>();
                    let ic_ground_pads = component
                        .footprint_pads
                        .iter()
                        .filter(|pad| pad.net == required_ic.ground)
                        .collect::<Vec<_>>();
                    let cap_rail_pads = actual_cap
                        .footprint_pads
                        .iter()
                        .filter(|pad| pad.net == rail)
                        .collect::<Vec<_>>();
                    let cap_ground_pads = actual_cap
                        .footprint_pads
                        .iter()
                        .filter(|pad| pad.net == required_ic.ground)
                        .collect::<Vec<_>>();
                    if ic_rail_pads.is_empty()
                        || ic_ground_pads.is_empty()
                        || cap_rail_pads.is_empty()
                        || cap_ground_pads.is_empty()
                    {
                        None
                    } else {
                        Some((
                            minimum_pad_distance(&ic_rail_pads, &cap_rail_pads),
                            minimum_pad_distance(&ic_ground_pads, &cap_ground_pads),
                        ))
                    }
                });
                if pad_locality.is_none() && input.identity.native_binding_required {
                    gaps.push(format!(
                        "{ic}: native decoupling input lacks named rail/return pad geometry"
                    ));
                    findings.push(Finding::indeterminate(
                        "DRC.RTD.LOCAL_DECOUPLING",
                        format!(
                            "{cap_component_id} lacks complete native rail/return pad geometry",
                            cap_component_id = cap.component
                        ),
                        cap.component.clone(),
                    ));
                    continue;
                }
                let outside_locality = match pad_locality {
                    Some((rail_distance, ground_distance)) => {
                        rail_distance > input.board.geometry.required_locality_mm
                            || ground_distance > input.board.geometry.required_locality_mm
                    }
                    None => cap_component.is_none_or(|actual| {
                        actual.position_mm.len() != 2
                            || distance(
                                [actual.position_mm[0], actual.position_mm[1]],
                                &component.position_mm,
                            ) > input.board.geometry.required_locality_mm
                    }),
                };
                if outside_locality {
                    findings.push(Finding::fail(
                        "DRC.RTD.LOCAL_DECOUPLING",
                        format!(
                            "bypass {} is outside {} mm locality of {ic}",
                            cap.component, input.board.geometry.required_locality_mm
                        ),
                        cap.component.clone(),
                    ));
                }
            }
        } else {
            gaps.push(format!(
                "{ic}: board position is absent, so physical bypass locality is indeterminate"
            ));
        }
    }
    // A differential input capacitor is a filter, not a supply bypass.  It
    // therefore has no required-IC rail entry above, but it still needs an
    // observed two-net binding and physical locality to the target ADC.  Keep
    // this in the shared native decoupling rule so every bypass/filter uses
    // the same source/native pad evidence.
    for filter in input
        .rtd
        .decoupling
        .iter()
        .filter(|d| d.rail != "+3V3" && d.rail != "RTD_AVDD" && d.ground != "gnd")
    {
        let Some(target) = input
            .board
            .components
            .iter()
            .find(|component| component.id == filter.ic)
        else {
            gaps.push(format!(
                "{}: filter target {} is absent from native board",
                filter.component, filter.ic
            ));
            findings.push(Finding::indeterminate(
                "DRC.RTD.LOCAL_DECOUPLING",
                "differential filter target lacks native component geometry",
                filter.component.clone(),
            ));
            continue;
        };
        let Some(cap_component) = input
            .board
            .components
            .iter()
            .find(|component| component.id == filter.component)
        else {
            findings.push(Finding::fail(
                "DRC.RTD.LOCAL_DECOUPLING",
                "differential filter component is absent from native board",
                filter.component.clone(),
            ));
            continue;
        };
        let actual_nets: std::collections::BTreeSet<_> = input
            .board
            .connections
            .iter()
            .filter(|connection| connection.component == filter.component)
            .map(|connection| connection.net.as_str())
            .collect();
        if !actual_nets.contains(filter.rail.as_str())
            || !actual_nets.contains(filter.ground.as_str())
        {
            findings.push(Finding::fail(
                "DRC.RTD.LOCAL_DECOUPLING",
                format!(
                    "differential filter {} is not connected to {} and {}",
                    filter.component, filter.rail, filter.ground
                ),
                filter.component.clone(),
            ));
            continue;
        }
        let target_first: Vec<_> = target
            .footprint_pads
            .iter()
            .filter(|pad| pad.net == filter.rail)
            .collect();
        let target_second: Vec<_> = target
            .footprint_pads
            .iter()
            .filter(|pad| pad.net == filter.ground)
            .collect();
        let filter_first: Vec<_> = cap_component
            .footprint_pads
            .iter()
            .filter(|pad| pad.net == filter.rail)
            .collect();
        let filter_second: Vec<_> = cap_component
            .footprint_pads
            .iter()
            .filter(|pad| pad.net == filter.ground)
            .collect();
        if target_first.is_empty()
            || target_second.is_empty()
            || filter_first.is_empty()
            || filter_second.is_empty()
        {
            gaps.push(format!(
                "{}: native differential filter lacks named source pad geometry",
                filter.component
            ));
            findings.push(Finding::indeterminate(
                "DRC.RTD.LOCAL_DECOUPLING",
                "differential filter lacks complete native target/pad geometry",
                filter.component.clone(),
            ));
            continue;
        }
        let distances = [
            minimum_pad_distance(&target_first, &filter_first),
            minimum_pad_distance(&target_second, &filter_second),
        ];
        if distances
            .iter()
            .any(|distance| *distance > input.board.geometry.required_locality_mm)
        {
            findings.push(Finding::fail(
                "DRC.RTD.LOCAL_DECOUPLING",
                format!(
                    "differential filter {} is outside {} mm locality of {}",
                    filter.component, input.board.geometry.required_locality_mm, filter.ic
                ),
                filter.component.clone(),
            ));
        }
    }
    let mut seen = std::collections::BTreeSet::new();
    for decoupling in &input.rtd.decoupling {
        if decoupling.capacitance_uf <= 0.0 || !decoupling.capacitance_uf.is_finite() {
            findings.push(Finding::fail(
                "DRC.RTD.LOCAL_DECOUPLING",
                "decoupling capacitance must be finite and positive",
                decoupling.component.clone(),
            ));
        }
        if !seen.insert(decoupling.component.clone()) {
            findings.push(Finding::fail(
                "DRC.RTD.LOCAL_DECOUPLING",
                "a decoupling component is registered more than once",
                decoupling.component.clone(),
            ));
        }
    }
}

fn check_sensitive_geometry(
    input: &RunInput,
    findings: &mut Vec<Finding>,
    gaps: &mut Vec<String>,
    checked: &mut Vec<String>,
) {
    checked.push("DRC.RTD.SENSITIVE_AGGRESSOR_GEOMETRY".into());
    if input.board.geometry.sensitive_nets.is_empty() {
        gaps.push(
            "no authored sensitive-net population was supplied; coupling rule is indeterminate"
                .into(),
        );
        findings.push(Finding::indeterminate(
            "DRC.RTD.SENSITIVE_AGGRESSOR_GEOMETRY",
            "authored sensitive-net population is empty",
            "geometry",
        ));
        return;
    }
    if input.board.geometry.aggressors.is_empty() {
        gaps.push(
            "no authored aggressor regions were supplied; coupling rule is indeterminate".into(),
        );
        findings.push(Finding::indeterminate(
            "DRC.RTD.SENSITIVE_AGGRESSOR_GEOMETRY",
            "authored aggressor-region population is empty",
            "geometry",
        ));
        return;
    }
    for sensitive in &input.board.geometry.sensitive_nets {
        let traces: Vec<_> = input
            .board
            .traces
            .iter()
            .filter(|t| &t.net == sensitive)
            .collect();
        if traces.is_empty() {
            findings.push(Finding::indeterminate(
                "DRC.RTD.SENSITIVE_AGGRESSOR_GEOMETRY",
                "sensitive net has no authored copper geometry",
                sensitive.clone(),
            ));
            continue;
        }
        for aggressor in &input.board.geometry.aggressors {
            if &aggressor.net == sensitive {
                continue;
            }
            if input.board.traces.iter().any(|t| {
                t.net == aggressor.net
                    && trace_near_region(t, aggressor.region_mm, aggressor.min_distance_mm)
            }) && traces
                .iter()
                .any(|t| trace_near_region(t, aggressor.region_mm, aggressor.min_distance_mm))
            {
                findings.push(Finding::fail(
                    "DRC.RTD.SENSITIVE_AGGRESSOR_GEOMETRY",
                    format!(
                        "sensitive net {sensitive} enters the authored aggressor region for {}",
                        aggressor.net
                    ),
                    sensitive.clone(),
                ));
            }
        }
    }
}

fn check_prohibited_connections(
    input: &RunInput,
    findings: &mut Vec<Finding>,
    gaps: &mut Vec<String>,
    checked: &mut Vec<String>,
) {
    checked.push("DRC.RTD.DOMAIN_BOUNDARY_CONNECTIONS".into());
    if input.board.geometry.prohibited_connections.is_empty() {
        gaps.push("no authored prohibited domain connection pairs were supplied; boundary rule is indeterminate".into());
        findings.push(Finding::indeterminate(
            "DRC.RTD.DOMAIN_BOUNDARY_CONNECTIONS",
            "authored prohibited-connection population is empty",
            "geometry",
        ));
        return;
    }
    for prohibited in &input.board.geometry.prohibited_connections {
        for component in &input.board.components {
            let has_first = input
                .board
                .connections
                .iter()
                .any(|c| c.component == component.id && c.net == prohibited.first_net);
            let has_second = input
                .board
                .connections
                .iter()
                .any(|c| c.component == component.id && c.net == prohibited.second_net);
            if has_first && has_second {
                findings.push(Finding::fail(
                    "DRC.RTD.DOMAIN_BOUNDARY_CONNECTIONS",
                    format!(
                        "{} connects prohibited nets {} and {}: {}",
                        component.id,
                        prohibited.first_net,
                        prohibited.second_net,
                        prohibited.reason
                    ),
                    component.id.clone(),
                ));
            }
        }
    }
}

fn check_native_geometry(
    input: &RunInput,
    findings: &mut Vec<Finding>,
    gaps: &mut Vec<String>,
    checked: &mut Vec<String>,
) {
    checked.push("DRC.RTD.NATIVE_GEOMETRY".into());
    if input.board.traces.is_empty() {
        gaps.push("no native RTD trace geometry was supplied; copper spacing and return-path checks remain indeterminate".into());
    }
    if input
        .board
        .components
        .iter()
        .all(|component| component.footprint_pads.is_empty())
    {
        gaps.push("native input has no pad coordinates, sizes, or layers; finite copper/pad return geometry remains indeterminate".into());
    }
    for component in &input.board.components {
        for pad in &component.footprint_pads {
            let connections: Vec<_> = input
                .board
                .connections
                .iter()
                .filter(|connection| {
                    connection.component == component.id && connection.pin == pad.pad
                })
                .collect();
            if connections.is_empty()
                || connections
                    .iter()
                    .any(|connection| connection.net != pad.net)
            {
                findings.push(Finding::fail(
                    "DRC.RTD.NATIVE_GEOMETRY",
                    format!(
                        "native pad {}.{} net {} has no matching Connection",
                        component.id, pad.pad, pad.net
                    ),
                    format!("{}.{}", component.id, pad.pad),
                ));
            }
        }
    }
    for net in [
        input.rtd.local_rail.upstream_net.as_str(),
        input.rtd.local_rail.post_ferrite_net.as_str(),
        input.rtd.reference.ground_net.as_str(),
    ] {
        let endpoints: std::collections::BTreeSet<_> = input
            .board
            .connections
            .iter()
            .filter(|connection| connection.net == net)
            .map(|connection| format!("{}.{}", connection.component, connection.pin))
            .collect();
        let clusters: Vec<_> = input
            .board
            .connectivity_clusters
            .iter()
            .filter(|cluster| cluster.net == net && cluster.source == "native")
            .collect();
        if clusters.is_empty() {
            findings.push(Finding::indeterminate(
                "DRC.RTD.NATIVE_GEOMETRY",
                format!("native connectivity evidence is missing for supply/return net {net}"),
                net,
            ));
            continue;
        }
        let covering = clusters.iter().position(|cluster| {
            endpoints
                .iter()
                .all(|endpoint| cluster.nodes.iter().any(|node| node == endpoint))
        });
        if covering.is_none() {
            findings.push(Finding::fail(
                "DRC.RTD.NATIVE_GEOMETRY",
                format!("native copper splits or omits required endpoints on {net}"),
                net,
            ));
        } else if let Some(covering) = covering {
            if clusters.iter().enumerate().any(|(index, cluster)| {
                index != covering && cluster.nodes.iter().any(|node| endpoints.contains(node))
            }) {
                findings.push(Finding::fail(
                    "DRC.RTD.NATIVE_GEOMETRY",
                    format!("native copper has split clusters on {net}"),
                    net,
                ));
            }
        }
    }
}

fn distance(a: [f64; 2], b: &[f64]) -> f64 {
    if b.len() != 2 {
        return f64::INFINITY;
    }
    ((a[0] - b[0]).powi(2) + (a[1] - b[1]).powi(2)).sqrt()
}

fn trace_near_region(trace: &zapote_core::Trace, region: [f64; 4], margin: f64) -> bool {
    let [x1, y1, x2, y2] = region;
    let half_width = trace.width_mm / 2.0;
    let rect = [
        x1 - margin - half_width,
        y1 - margin - half_width,
        x2 + margin + half_width,
        y2 + margin + half_width,
    ];
    trace
        .points_mm
        .windows(2)
        .any(|segment| segment_intersects_rect(segment[0], segment[1], rect))
}

fn segment_intersects_rect(start: [f64; 2], end: [f64; 2], rect: [f64; 4]) -> bool {
    if (start[0] >= rect[0] && start[0] <= rect[2] && start[1] >= rect[1] && start[1] <= rect[3])
        || (end[0] >= rect[0] && end[0] <= rect[2] && end[1] >= rect[1] && end[1] <= rect[3])
    {
        return true;
    }
    let edges = [
        ([rect[0], rect[1]], [rect[2], rect[1]]),
        ([rect[2], rect[1]], [rect[2], rect[3]]),
        ([rect[2], rect[3]], [rect[0], rect[3]]),
        ([rect[0], rect[3]], [rect[0], rect[1]]),
    ];
    if edges.iter().any(|(a, b)| {
        donor_geometry::segments_intersect(
            start[0], start[1], end[0], end[1], a[0], a[1], b[0], b[1],
        )
    }) {
        return true;
    }
    let (mut t_min, mut t_max): (f64, f64) = (0.0, 1.0);
    let delta = [end[0] - start[0], end[1] - start[1]];
    for axis in 0..2 {
        let low = rect[axis];
        let high = rect[axis + 2];
        if delta[axis].abs() < f64::EPSILON {
            if start[axis] < low || start[axis] > high {
                return false;
            }
            continue;
        }
        let mut near = (low - start[axis]) / delta[axis];
        let mut far = (high - start[axis]) / delta[axis];
        if near > far {
            std::mem::swap(&mut near, &mut far);
        }
        t_min = t_min.max(near);
        t_max = t_max.min(far);
        if t_min > t_max {
            return false;
        }
    }
    true
}

#[cfg(test)]
mod tests {
    use super::*;
    use zapote_core::*;
    #[test]
    fn region_predicate_uses_authored_margin() {
        let trace = Trace {
            id: "trace-a".into(),
            net: "RTD_SCK".into(),
            points_mm: vec![[10.0, 10.0], [10.0, 10.0]],
            layer: "F.Cu".into(),
            width_mm: 0.2,
        };
        assert!(trace_near_region(&trace, [11.0, 11.0, 12.0, 12.0], 1.5));
        assert!(!trace_near_region(&trace, [11.0, 11.0, 12.0, 12.0], 0.5));
    }
    #[test]
    fn crossing_segment_is_detected_without_vertex_inside() {
        let trace = Trace {
            id: "trace-b".into(),
            net: "RTD_SCK".into(),
            points_mm: vec![[0.0, 5.0], [20.0, 5.0]],
            layer: "F.Cu".into(),
            width_mm: 0.1,
        };
        assert!(trace_near_region(&trace, [8.0, 4.0, 12.0, 6.0], 0.0));
    }
    #[test]
    fn copper_width_is_included_at_boundary() {
        let near = Trace {
            id: "trace-near".into(),
            net: "RTD_SCK".into(),
            points_mm: vec![[0.0, 6.1], [20.0, 6.1]],
            layer: "F.Cu".into(),
            width_mm: 0.3,
        };
        let clear = Trace {
            width_mm: 0.1,
            ..near.clone()
        };
        assert!(trace_near_region(&near, [8.0, 4.0, 12.0, 6.0], 0.0));
        assert!(!trace_near_region(&clear, [8.0, 4.0, 12.0, 6.0], 0.0));
    }
}
