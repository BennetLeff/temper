//! RTD physical placement, rail, decoupling, locality, and noise checks.

mod donor_geometry;

use zapote_core::{CheckReport, Finding, RunInput};

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
    CheckReport::from_findings(findings, checked, gaps)
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
        if !caps
            .iter()
            .any(|d| d.rail == rail && d.ground == required_ic.ground && d.capacitance_uf > 0.0)
        {
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
            let cap = caps.iter().min_by(|a, b| {
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
                let actual_cap_position = cap_component.map(|actual| actual.position_mm.as_slice());
                if actual_cap_position.is_none_or(|position| {
                    position.len() != 2
                        || distance([position[0], position[1]], &component.position_mm)
                            > input.board.geometry.required_locality_mm
                }) {
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
