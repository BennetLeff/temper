//! Geometry, layer, locality, and primary/secondary separation checks for
//! the standalone current-sensing unit.

use crate::donor_clearance;
use std::collections::BTreeSet;
use zapote_core::current_sense::CurrentSenseInput;
use zapote_core::{CheckReport, Finding, Pad, Trace};

const RULE_GEOMETRY: &str = "DRC.CURRENT_SENSE.NATIVE_GEOMETRY";
const RULE_CLEARANCE: &str = "DRC.CURRENT_SENSE.CLEARANCE";
const RULE_SEPARATION: &str = "DRC.CURRENT_SENSE.PRIMARY_SECONDARY_SEPARATION";
const RULE_LOCALITY: &str = "DRC.CURRENT_SENSE.LOCALITY";
const RULE_COPPER: &str = "DRC.CURRENT_SENSE.REQUIRED_COPPER";

pub fn validate(input: &CurrentSenseInput) -> CheckReport {
    let mut findings = crate::stackup::validate_native_export(
        &input.native_export_utf8,
        &input.identity.board_sha256,
    )
    .findings;
    let mut gaps = Vec::new();
    let checked = vec![
        crate::stackup::RULE.into(),
        RULE_GEOMETRY.into(),
        RULE_CLEARANCE.into(),
        RULE_SEPARATION.into(),
        RULE_LOCALITY.into(),
        RULE_COPPER.into(),
    ];
    check_native_geometry(input, &mut findings);
    check_required_copper(input, &mut findings, &mut gaps);
    check_clearance(input, &mut findings);
    check_primary_secondary(input, &mut findings, &mut gaps);
    check_locality(input, &mut findings);
    CheckReport::from_findings(findings, checked, gaps)
}

fn check_native_geometry(input: &CurrentSenseInput, findings: &mut Vec<Finding>) {
    let geometry = &input.profile.geometry;
    if input.native.copper_layer_count != geometry.copper_layers {
        findings.push(Finding::fail(
            RULE_GEOMETRY,
            format!(
                "native layer count {} does not match source profile {}",
                input.native.copper_layer_count, geometry.copper_layers
            ),
            "native.copper_layer_count",
        ));
    }
    let allowed: BTreeSet<_> = geometry.allowed_layers.iter().map(String::as_str).collect();
    for trace in &input.native.traces {
        if trace.points_mm.len() < 2
            || trace
                .points_mm
                .iter()
                .flatten()
                .any(|value| !value.is_finite())
            || !trace.width_mm.is_finite()
            || trace.width_mm <= 0.0
        {
            findings.push(Finding::fail(
                RULE_GEOMETRY,
                "native trace has non-finite geometry or non-positive width",
                trace.id.clone(),
            ));
        }
        if trace.width_mm < geometry.min_trace_width_mm {
            findings.push(Finding::fail(
                RULE_GEOMETRY,
                format!(
                    "trace width {:.6} mm is below source minimum {:.6} mm",
                    trace.width_mm, geometry.min_trace_width_mm
                ),
                trace.id.clone(),
            ));
        }
        if !allowed.is_empty() && !allowed.contains(trace.layer.as_str()) {
            findings.push(Finding::fail(
                RULE_GEOMETRY,
                format!(
                    "trace layer {} is outside source allowed_layers",
                    trace.layer
                ),
                trace.id.clone(),
            ));
        }
    }
    for via in &input.native.vias {
        if via.position_mm.iter().any(|value| !value.is_finite())
            || !via.drill_mm.is_finite()
            || via.drill_mm <= 0.0
            || !via.diameter_mm.is_finite()
            || via.diameter_mm <= 0.0
        {
            findings.push(Finding::fail(
                RULE_GEOMETRY,
                "native via has non-finite geometry or non-positive dimensions",
                via.id.clone(),
            ));
        }
    }
    for component in &input.native.components {
        if component.position_mm.len() != 2
            || component.position_mm.iter().any(|value| !value.is_finite())
        {
            findings.push(Finding::fail(
                RULE_GEOMETRY,
                "native component position is not finite [x,y]",
                component.id.clone(),
            ));
        }
        for pad in &component.footprint_pads {
            if pad.position_mm.iter().any(|value| !value.is_finite())
                || pad
                    .size_mm
                    .iter()
                    .any(|value| !value.is_finite() || *value <= 0.0)
            {
                findings.push(Finding::fail(
                    RULE_GEOMETRY,
                    "native pad position/size is not finite and positive",
                    format!("{}.{}", component.id, pad.pad),
                ));
            }
            if donor_clearance::raw_kicad_shape_to_donor_shape(pad.shape as i64).is_err() {
                findings.push(Finding::fail(
                    RULE_GEOMETRY,
                    format!("unsupported native KiCad pad shape code {}", pad.shape),
                    format!("{}.{}", component.id, pad.pad),
                ));
            }
            if pad.shape == 4 && pad.roundrect_ratio.is_none() {
                findings.push(Finding::fail(
                    RULE_GEOMETRY,
                    "roundrect pad is missing native radius ratio",
                    format!("{}.{}", component.id, pad.pad),
                ));
            }
            if let Some(ratio) = pad.roundrect_ratio {
                if !ratio.is_finite() || !(0.0..=0.5).contains(&ratio) {
                    findings.push(Finding::fail(
                        RULE_GEOMETRY,
                        "native roundrect radius ratio is outside [0,0.5]",
                        format!("{}.{}", component.id, pad.pad),
                    ));
                }
            }
        }
    }
}

fn check_required_copper(
    input: &CurrentSenseInput,
    findings: &mut Vec<Finding>,
    gaps: &mut Vec<String>,
) {
    let required: BTreeSet<_> = input
        .profile
        .nets
        .iter()
        .filter(|net| net.required_copper)
        .map(|net| net.name.as_str())
        .chain(
            input
                .profile
                .geometry
                .required_routed_nets
                .iter()
                .map(String::as_str),
        )
        .collect();
    if required.is_empty() {
        gaps.push("source profile declares no required routed nets".into());
        findings.push(Finding::indeterminate(
            RULE_COPPER,
            "required routed-net population is empty; copper existence cannot be qualified",
            "current-sense-profile",
        ));
        return;
    }
    for net in required {
        let has_trace = input.native.traces.iter().any(|trace| trace.net == net);
        let has_via = input.native.vias.iter().any(|via| via.net == net);
        let has_zone = input
            .native
            .zones
            .iter()
            .any(|zone| zone.net == net && !zone.filled_polygons.is_empty());
        if !has_trace && !has_via && !has_zone {
            findings.push(Finding::fail(
                RULE_COPPER,
                "required net has no native trace, via, or filled zone; a net label is not copper evidence",
                net,
            ));
        }
    }
}

fn all_pads(input: &CurrentSenseInput) -> Vec<(&str, &Pad)> {
    input
        .native
        .components
        .iter()
        .flat_map(|component| {
            component
                .footprint_pads
                .iter()
                .map(move |pad| (component.id.as_str(), pad))
        })
        .collect()
}

fn check_clearance(input: &CurrentSenseInput, findings: &mut Vec<Finding>) {
    let report = native_clearance(&input.native, input.profile.geometry.clearance_mm);
    findings.extend(
        report
            .findings
            .into_iter()
            .filter(|f| f.status != zapote_core::Status::Pass)
            .map(|mut f| {
                f.rule = RULE_CLEARANCE.into();
                f
            }),
    );
}

/// Shared native-copper checks, using the existing donor geometry kernel.
/// This is a fabrication spacing floor, not an insulation qualification.
pub fn native_clearance(
    native: &zapote_core::unit::UnitNativeEvidence,
    required: f64,
) -> CheckReport {
    const RULE: &str = "DRC.NATIVE.CLEARANCE";
    let mut findings = Vec::new();
    if !required.is_finite() || required <= 0.0 {
        return CheckReport::from_findings(
            vec![Finding::fail(RULE, "invalid clearance floor", "native")],
            vec![RULE.into()],
            vec![],
        );
    }
    let pads: Vec<_> = native
        .components
        .iter()
        .flat_map(|c| c.footprint_pads.iter().map(move |p| (c.id.as_str(), p)))
        .collect();

    for (index, (first_component, first)) in pads.iter().enumerate() {
        for (second_component, second) in pads.iter().skip(index + 1) {
            if first.net == second.net || !pad_layers_overlap(first, second) {
                continue;
            }
            let actual = pad_clearance_mm(first, second);
            if actual < required {
                findings.push(Finding::fail(
                    RULE,
                    format!("pad clearance {actual:.6} mm is below {required:.6} mm"),
                    format!(
                        "{first_component}.{} / {second_component}.{}",
                        first.pad, second.pad
                    ),
                ));
            }
        }
    }

    for (index, first) in native.traces.iter().enumerate() {
        for second in native.traces.iter().skip(index + 1) {
            if first.net == second.net || first.layer != second.layer {
                continue;
            }
            let actual = trace_clearance_mm(first, second);
            if actual < required {
                findings.push(Finding::fail(
                    RULE,
                    format!("trace clearance {actual:.6} mm is below {required:.6} mm"),
                    format!("{} / {}", first.id, second.id),
                ));
            }
        }
    }

    for (component_id, pad) in &pads {
        for trace in &native.traces {
            if pad.net == trace.net || !pad.layers.iter().any(|layer| layer == &trace.layer) {
                continue;
            }
            let actual = pad_trace_clearance_mm(pad, trace);
            if actual < required {
                findings.push(Finding::fail(
                    RULE,
                    format!("pad/trace clearance {actual:.6} mm is below {required:.6} mm"),
                    format!("{component_id}.{} / {}", pad.pad, trace.id),
                ));
            }
        }
        for via in &native.vias {
            if pad.net == via.net || !pad_via_layers_overlap(pad, via) {
                continue;
            }
            let actual = pad_via_clearance_mm(pad, via);
            if actual < required {
                findings.push(Finding::fail(
                    RULE,
                    format!("pad/via clearance {actual:.6} mm is below {required:.6} mm"),
                    format!("{component_id}.{} / {}", pad.pad, via.id),
                ));
            }
        }
    }

    // A via is a copper circle on every layer it spans.  This pair was absent
    // from the former native scan, so a crossing trace/via short could pass.
    for trace in &native.traces {
        for via in &native.vias {
            if trace.net == via.net || !via_touches_layer(via, &trace.layer) {
                continue;
            }
            let actual = trace_via_clearance_mm(trace, via);
            if actual < required {
                findings.push(Finding::fail(
                    RULE,
                    format!("trace/via clearance {actual:.6} mm is below {required:.6} mm"),
                    format!("{} / {}", trace.id, via.id),
                ));
            }
        }
    }
    for (index, first) in native.vias.iter().enumerate() {
        for second in native.vias.iter().skip(index + 1) {
            if first.net == second.net || !via_layers_overlap(first, second) {
                continue;
            }
            let actual = via_via_clearance_mm(first, second);
            if actual < required {
                findings.push(Finding::fail(
                    RULE,
                    format!("via clearance {actual:.6} mm is below {required:.6} mm"),
                    format!("{} / {}", first.id, second.id),
                ));
            }
        }
    }

    // Filled polygons are copper geometry, not just a set of sampled points.
    // Check the complete boundary and interior for every primitive and zone
    // pair, including holes and routes which cross between vertices.
    for zone in &native.zones {
        for (component_id, pad) in &pads {
            if pad.net == zone.net || !pad.layers.iter().any(|layer| layer == &zone.layer) {
                continue;
            }
            let actual = zone_pad_clearance_mm(zone, pad);
            if actual < required {
                findings.push(Finding::fail(
                    RULE,
                    format!("pad/zone clearance {actual:.6} mm is below {required:.6} mm"),
                    format!("{component_id}.{} / {}", pad.pad, zone.id),
                ));
            }
        }
        for trace in &native.traces {
            if trace.net == zone.net || trace.layer != zone.layer {
                continue;
            }
            let actual = zone_trace_clearance_mm(zone, trace);
            if actual < required {
                findings.push(Finding::fail(
                    RULE,
                    format!("trace/zone clearance {actual:.6} mm is below {required:.6} mm"),
                    format!("{} / {}", trace.id, zone.id),
                ));
            }
        }
        for via in &native.vias {
            if via.net == zone.net || !via_touches_layer(via, &zone.layer) {
                continue;
            }
            let actual = zone_via_clearance_mm(zone, via);
            if actual < required {
                findings.push(Finding::fail(
                    RULE,
                    format!("via/zone clearance {actual:.6} mm is below {required:.6} mm"),
                    format!("{} / {}", via.id, zone.id),
                ));
            }
        }
    }
    for (index, first) in native.zones.iter().enumerate() {
        for second in native.zones.iter().skip(index + 1) {
            if first.net == second.net || first.layer != second.layer {
                continue;
            }
            let actual = zone_zone_clearance_mm(first, second);
            if actual < required {
                findings.push(Finding::fail(
                    RULE,
                    format!("zone clearance {actual:.6} mm is below {required:.6} mm"),
                    format!("{} / {}", first.id, second.id),
                ));
            }
        }
    }
    if findings.is_empty() {
        findings.push(Finding::pass(
            RULE,
            format!("native copper clears {required} mm fabrication floor"),
            "native",
        ));
    }
    CheckReport::from_findings(findings, vec![RULE.into()], vec![])
}

fn check_primary_secondary(
    input: &CurrentSenseInput,
    findings: &mut Vec<Finding>,
    gaps: &mut Vec<String>,
) {
    let primary: BTreeSet<_> = input
        .profile
        .geometry
        .primary_nets
        .iter()
        .map(String::as_str)
        .collect();
    let secondary: BTreeSet<_> = input
        .profile
        .geometry
        .secondary_nets
        .iter()
        .map(String::as_str)
        .collect();
    let opposite = |first: &str, second: &str| {
        (primary.contains(first) && secondary.contains(second))
            || (secondary.contains(first) && primary.contains(second))
    };
    let pads = all_pads(input);
    let required = input.profile.geometry.primary_secondary_clearance_mm;
    let mut compared = 0usize;

    for (index, (first_component, first)) in pads.iter().enumerate() {
        for (second_component, second) in pads.iter().skip(index + 1) {
            if !opposite(first.net.as_str(), second.net.as_str()) {
                continue;
            }
            compared += 1;
            let actual = pad_clearance_mm(first, second);
            if actual < required {
                findings.push(Finding::fail(
                    RULE_SEPARATION,
                    format!(
                        "primary/secondary pad clearance {actual:.6} mm is below {required:.6} mm"
                    ),
                    format!(
                        "{first_component}.{} / {second_component}.{}",
                        first.pad, second.pad
                    ),
                ));
            }
        }
    }
    for (index, first) in input.native.traces.iter().enumerate() {
        for second in input.native.traces.iter().skip(index + 1) {
            if !opposite(first.net.as_str(), second.net.as_str()) {
                continue;
            }
            compared += 1;
            let actual = trace_clearance_mm(first, second);
            if actual < required {
                findings.push(Finding::fail(
                    RULE_SEPARATION,
                    format!("primary/secondary trace clearance {actual:.6} mm is below {required:.6} mm"),
                    format!("{} / {}", first.id, second.id),
                ));
            }
        }
    }
    for (component_id, pad) in &pads {
        for trace in &input.native.traces {
            if !opposite(pad.net.as_str(), trace.net.as_str()) {
                continue;
            }
            compared += 1;
            let actual = pad_trace_clearance_mm(pad, trace);
            if actual < required {
                findings.push(Finding::fail(
                    RULE_SEPARATION,
                    format!("primary/secondary pad/trace clearance {actual:.6} mm is below {required:.6} mm"),
                    format!("{component_id}.{} / {}", pad.pad, trace.id),
                ));
            }
        }
        for via in &input.native.vias {
            if !opposite(pad.net.as_str(), via.net.as_str()) {
                continue;
            }
            compared += 1;
            let actual = pad_via_clearance_mm(pad, via);
            if actual < required {
                findings.push(Finding::fail(
                    RULE_SEPARATION,
                    format!("primary/secondary pad/via clearance {actual:.6} mm is below {required:.6} mm"),
                    format!("{component_id}.{} / {}", pad.pad, via.id),
                ));
            }
        }
    }
    for trace in &input.native.traces {
        for via in &input.native.vias {
            if !opposite(trace.net.as_str(), via.net.as_str()) {
                continue;
            }
            compared += 1;
            let actual = trace_via_clearance_mm(trace, via);
            if actual < required {
                findings.push(Finding::fail(
                    RULE_SEPARATION,
                    format!("primary/secondary trace/via clearance {actual:.6} mm is below {required:.6} mm"),
                    format!("{} / {}", trace.id, via.id),
                ));
            }
        }
    }
    for (index, first) in input.native.vias.iter().enumerate() {
        for second in input.native.vias.iter().skip(index + 1) {
            if !opposite(first.net.as_str(), second.net.as_str()) {
                continue;
            }
            compared += 1;
            let actual = via_via_clearance_mm(first, second);
            if actual < required {
                findings.push(Finding::fail(
                    RULE_SEPARATION,
                    format!(
                        "primary/secondary via clearance {actual:.6} mm is below {required:.6} mm"
                    ),
                    format!("{} / {}", first.id, second.id),
                ));
            }
        }
    }

    // Zones are physical copper too.  This catches a primary route or pad
    // sitting beneath an LV/return pour, including the common GND-pour case.
    for (index, first) in input.native.zones.iter().enumerate() {
        for second in input.native.zones.iter().skip(index + 1) {
            if !opposite(first.net.as_str(), second.net.as_str()) {
                continue;
            }
            compared += 1;
            let actual = zone_zone_clearance_mm(first, second);
            if actual < required {
                findings.push(Finding::fail(
                    RULE_SEPARATION,
                    format!(
                        "primary/secondary zone clearance {actual:.6} mm is below {required:.6} mm"
                    ),
                    format!("{} / {}", first.id, second.id),
                ));
            }
        }
        for (component_id, pad) in &pads {
            if !opposite(first.net.as_str(), pad.net.as_str()) {
                continue;
            }
            compared += 1;
            let actual = zone_pad_clearance_mm(first, pad);
            if actual < required {
                findings.push(Finding::fail(RULE_SEPARATION, format!("primary/secondary zone/pad clearance {actual:.6} mm is below {required:.6} mm"), format!("{} / {component_id}.{}", first.id, pad.pad)));
            }
        }
        for trace in &input.native.traces {
            if !opposite(first.net.as_str(), trace.net.as_str()) {
                continue;
            }
            compared += 1;
            let actual = zone_trace_clearance_mm(first, trace);
            if actual < required {
                findings.push(Finding::fail(RULE_SEPARATION, format!("primary/secondary zone/trace clearance {actual:.6} mm is below {required:.6} mm"), format!("{} / {}", first.id, trace.id)));
            }
        }
        for via in &input.native.vias {
            if !opposite(first.net.as_str(), via.net.as_str()) {
                continue;
            }
            compared += 1;
            let actual = zone_via_clearance_mm(first, via);
            if actual < required {
                findings.push(Finding::fail(RULE_SEPARATION, format!("primary/secondary zone/via clearance {actual:.6} mm is below {required:.6} mm"), format!("{} / {}", first.id, via.id)));
            }
        }
    }
    if compared == 0 {
        gaps.push("primary/secondary separation has no actual copper pair to compare".into());
        findings.push(Finding::indeterminate(
            RULE_SEPARATION,
            "primary/secondary net sets exist but native copper geometry is absent",
            "primary-secondary",
        ));
    }
}

fn check_locality(input: &CurrentSenseInput, findings: &mut Vec<Finding>) {
    for requirement in &input.profile.locality {
        let first = input
            .native
            .components
            .iter()
            .find(|component| component.id == requirement.component);
        let second = input
            .native
            .components
            .iter()
            .find(|component| component.id == requirement.target_component);
        let (Some(first), Some(second)) = (first, second) else {
            findings.push(Finding::fail(
                RULE_LOCALITY,
                "locality requirement names a missing native component",
                format!(
                    "{} -> {}",
                    requirement.component, requirement.target_component
                ),
            ));
            continue;
        };
        if first.position_mm.len() != 2 || second.position_mm.len() != 2 {
            findings.push(Finding::fail(
                RULE_LOCALITY,
                "locality component position is malformed",
                format!(
                    "{} -> {}",
                    requirement.component, requirement.target_component
                ),
            ));
            continue;
        }
        let dx = first.position_mm[0] - second.position_mm[0];
        let dy = first.position_mm[1] - second.position_mm[1];
        let actual = dx.hypot(dy);
        if actual > requirement.max_distance_mm {
            findings.push(Finding::fail(
                RULE_LOCALITY,
                format!(
                    "component locality {:.6} mm exceeds {:.6} mm",
                    actual, requirement.max_distance_mm
                ),
                format!(
                    "{} -> {}",
                    requirement.component, requirement.target_component
                ),
            ));
        }
    }
}

fn pad_clearance_mm(first: &Pad, second: &Pad) -> f64 {
    donor_clearance::pad_pair_distance(pad_spec(first), pad_spec(second))
}

fn pad_spec(pad: &Pad) -> donor_clearance::PadSpec {
    // Keep pcbnew's raw enum at the core transport boundary and map it once
    // here to the donor's independent enum.  An unsupported raw shape is
    // represented by 99; the donor then returns zero clearance fail-closed.
    let shape = donor_clearance::raw_kicad_shape_to_donor_shape(pad.shape as i64).unwrap_or(99);
    let ratio = pad
        .roundrect_ratio
        .unwrap_or(if pad.shape == 4 { -1.0 } else { 0.0 });
    (
        pad.size_mm[0],
        pad.size_mm[1],
        shape,
        pad.position_mm[0],
        pad.position_mm[1],
        pad.orientation_deg.to_radians(),
        ratio,
    )
}

fn pad_layers_overlap(first: &Pad, second: &Pad) -> bool {
    first.layers.is_empty()
        || second.layers.is_empty()
        || first
            .layers
            .iter()
            .any(|layer| second.layers.contains(layer))
}

fn via_layers_overlap(first: &zapote_core::Via, second: &zapote_core::Via) -> bool {
    first.from_layer == second.from_layer
        || first.from_layer == second.to_layer
        || first.to_layer == second.from_layer
        || first.to_layer == second.to_layer
}

/// KiCad rotates footprint children clockwise: world = position + R(-theta) * local.
#[cfg(test)]
fn pad_corners(pad: &Pad) -> [[f64; 2]; 4] {
    let theta = pad.orientation_deg.to_radians();
    let (sin, cos) = theta.sin_cos();
    let hx = pad.size_mm[0] / 2.0;
    let hy = pad.size_mm[1] / 2.0;
    [[-hx, -hy], [hx, -hy], [hx, hy], [-hx, hy]].map(|[x, y]| {
        [
            pad.position_mm[0] + cos * x + sin * y,
            pad.position_mm[1] - sin * x + cos * y,
        ]
    })
}

fn pad_trace_clearance_mm(pad: &Pad, trace: &Trace) -> f64 {
    let mut distance = f64::INFINITY;
    for segment in trace.points_mm.windows(2) {
        let actual = donor_clearance::pad_to_capsule_distance(
            pad_spec(pad),
            (segment[0][0], segment[0][1]),
            (segment[1][0], segment[1][1]),
            trace.width_mm,
        )
        .unwrap_or(0.0);
        distance = distance.min(actual);
    }
    distance
}

fn pad_via_clearance_mm(pad: &Pad, via: &zapote_core::Via) -> f64 {
    donor_clearance::pad_to_capsule_distance(
        pad_spec(pad),
        (via.position_mm[0], via.position_mm[1]),
        (via.position_mm[0], via.position_mm[1]),
        via.diameter_mm,
    )
    .unwrap_or(0.0)
}

fn via_via_clearance_mm(first: &zapote_core::Via, second: &zapote_core::Via) -> f64 {
    ((first.position_mm[0] - second.position_mm[0])
        .hypot(first.position_mm[1] - second.position_mm[1])
        - first.diameter_mm / 2.0
        - second.diameter_mm / 2.0)
        .max(0.0)
}

fn trace_via_clearance_mm(trace: &Trace, via: &zapote_core::Via) -> f64 {
    trace
        .points_mm
        .windows(2)
        .map(|segment| {
            (segment_distance(segment[0], segment[1], via.position_mm, via.position_mm)
                - trace.width_mm / 2.0
                - via.diameter_mm / 2.0)
                .max(0.0)
        })
        .fold(f64::INFINITY, f64::min)
}

fn via_touches_layer(via: &zapote_core::Via, layer: &str) -> bool {
    via.from_layer == layer || via.to_layer == layer
}

fn pad_via_layers_overlap(pad: &Pad, via: &zapote_core::Via) -> bool {
    pad.layers.iter().any(|layer| via_touches_layer(via, layer))
}

fn zone_contains(zone: &zapote_core::NativeZone, point: [f64; 2]) -> bool {
    zone.filled_polygons.iter().any(|polygon| {
        let inside_outer = ring_contains(&polygon.outer_mm, point);
        inside_outer
            && !polygon
                .holes_mm
                .iter()
                .any(|hole| ring_contains(hole, point))
    })
}

fn ring_contains(ring: &[[f64; 2]], point: [f64; 2]) -> bool {
    if ring.len() < 3 {
        return false;
    }
    let mut inside = false;
    for index in 0..ring.len() {
        let a = ring[index];
        let b = ring[(index + 1) % ring.len()];
        if point_on_segment(a, b, point) {
            return true;
        }
        if (a[1] > point[1]) != (b[1] > point[1]) {
            let x = (b[0] - a[0]) * (point[1] - a[1]) / (b[1] - a[1]) + a[0];
            if point[0] < x {
                inside = !inside;
            }
        }
    }
    inside
}

fn point_on_segment(a: [f64; 2], b: [f64; 2], point: [f64; 2]) -> bool {
    let cross = (b[0] - a[0]) * (point[1] - a[1]) - (b[1] - a[1]) * (point[0] - a[0]);
    cross.abs() <= 1e-12
        && point[0] >= a[0].min(b[0]) - 1e-12
        && point[0] <= a[0].max(b[0]) + 1e-12
        && point[1] >= a[1].min(b[1]) - 1e-12
        && point[1] <= a[1].max(b[1]) + 1e-12
}

fn ring_edges(ring: &[[f64; 2]]) -> impl Iterator<Item = ([f64; 2], [f64; 2])> + '_ {
    (0..ring.len()).map(|index| (ring[index], ring[(index + 1) % ring.len()]))
}

fn zone_edges(zone: &zapote_core::NativeZone) -> impl Iterator<Item = ([f64; 2], [f64; 2])> + '_ {
    zone.filled_polygons.iter().flat_map(|polygon| {
        std::iter::once(polygon.outer_mm.as_slice())
            .chain(polygon.holes_mm.iter().map(Vec::as_slice))
            .flat_map(ring_edges)
    })
}

fn zone_pad_clearance_mm(zone: &zapote_core::NativeZone, pad: &Pad) -> f64 {
    if pad.position_mm.iter().any(|v| !v.is_finite()) || zone_contains(zone, pad.position_mm) {
        return 0.0;
    }
    let spec = pad_spec(pad);
    zone_edges(zone)
        .map(|(a, b)| {
            donor_clearance::pad_to_capsule_distance(spec, (a[0], a[1]), (b[0], b[1]), 1.0e-9)
                .unwrap_or(0.0)
        })
        .fold(f64::INFINITY, f64::min)
}

fn zone_trace_clearance_mm(zone: &zapote_core::NativeZone, trace: &Trace) -> f64 {
    let mut best = f64::INFINITY;
    for segment in trace.points_mm.windows(2) {
        let a = segment[0];
        let b = segment[1];
        if zone_contains(zone, a) || zone_contains(zone, b) || segments_intersect_zone(zone, a, b) {
            return 0.0;
        }
        for (edge_a, edge_b) in zone_edges(zone) {
            best =
                best.min((segment_distance(a, b, edge_a, edge_b) - trace.width_mm / 2.0).max(0.0));
        }
    }
    best
}

fn zone_via_clearance_mm(zone: &zapote_core::NativeZone, via: &zapote_core::Via) -> f64 {
    if zone_contains(zone, via.position_mm) {
        return 0.0;
    }
    zone_edges(zone)
        .map(|(a, b)| {
            (point_segment_distance(via.position_mm, a, b) - via.diameter_mm / 2.0).max(0.0)
        })
        .fold(f64::INFINITY, f64::min)
}

fn segments_intersect_zone(zone: &zapote_core::NativeZone, a: [f64; 2], b: [f64; 2]) -> bool {
    zone_edges(zone).any(|(c, d)| segments_intersect(a, b, c, d))
}

fn zone_zone_clearance_mm(
    first: &zapote_core::NativeZone,
    second: &zapote_core::NativeZone,
) -> f64 {
    if zones_filled_overlap(first, second) {
        return 0.0;
    }
    zone_edges(first)
        .flat_map(|(a, b)| zone_edges(second).map(move |(c, d)| segment_distance(a, b, c, d)))
        .fold(f64::INFINITY, f64::min)
}

fn zones_filled_overlap(first: &zapote_core::NativeZone, second: &zapote_core::NativeZone) -> bool {
    first.filled_polygons.iter().any(|polygon| {
        polygon
            .outer_mm
            .iter()
            .copied()
            .any(|point| zone_contains(second, point))
    }) || second.filled_polygons.iter().any(|polygon| {
        polygon
            .outer_mm
            .iter()
            .copied()
            .any(|point| zone_contains(first, point))
    }) || zone_edges(first)
        .any(|(a, b)| zone_edges(second).any(|(c, d)| segments_intersect(a, b, c, d)))
}

fn trace_clearance_mm(first: &Trace, second: &Trace) -> f64 {
    let mut distance = f64::INFINITY;
    for first_segment in first.points_mm.windows(2) {
        for second_segment in second.points_mm.windows(2) {
            distance = distance.min(segment_distance(
                first_segment[0],
                first_segment[1],
                second_segment[0],
                second_segment[1],
            ));
        }
    }
    (distance - first.width_mm / 2.0 - second.width_mm / 2.0).max(0.0)
}

fn segment_distance(a: [f64; 2], b: [f64; 2], c: [f64; 2], d: [f64; 2]) -> f64 {
    if segments_intersect(a, b, c, d) {
        return 0.0;
    }
    point_segment_distance(a, c, d)
        .min(point_segment_distance(b, c, d))
        .min(point_segment_distance(c, a, b))
        .min(point_segment_distance(d, a, b))
}

fn point_segment_distance(point: [f64; 2], start: [f64; 2], end: [f64; 2]) -> f64 {
    let dx = end[0] - start[0];
    let dy = end[1] - start[1];
    let length_squared = dx * dx + dy * dy;
    if length_squared <= f64::EPSILON {
        return (point[0] - start[0]).hypot(point[1] - start[1]);
    }
    let t = (((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / length_squared)
        .clamp(0.0, 1.0);
    (point[0] - (start[0] + t * dx)).hypot(point[1] - (start[1] + t * dy))
}

fn orientation(a: [f64; 2], b: [f64; 2], c: [f64; 2]) -> f64 {
    (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
}

fn segments_intersect(a: [f64; 2], b: [f64; 2], c: [f64; 2], d: [f64; 2]) -> bool {
    let ab_c = orientation(a, b, c);
    let ab_d = orientation(a, b, d);
    let cd_a = orientation(c, d, a);
    let cd_b = orientation(c, d, b);
    let eps = 1e-12;
    (ab_c * ab_d < -eps && cd_a * cd_b < -eps)
        || (ab_c.abs() <= eps && on_segment(a, b, c))
        || (ab_d.abs() <= eps && on_segment(a, b, d))
        || (cd_a.abs() <= eps && on_segment(c, d, a))
        || (cd_b.abs() <= eps && on_segment(c, d, b))
}

fn on_segment(start: [f64; 2], end: [f64; 2], point: [f64; 2]) -> bool {
    point[0] >= start[0].min(end[0]) - 1e-12
        && point[0] <= start[0].max(end[0]) + 1e-12
        && point[1] >= start[1].min(end[1]) - 1e-12
        && point[1] <= start[1].max(end[1]) + 1e-12
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn input_with_close_primary_secondary_pads() -> CurrentSenseInput {
        serde_json::from_value(json!({
            "schema":"zapote.current-sense.input.v1",
            "profile":{
                "schema":"zapote.current-sense.profile.v1","profile_id":"CurrentSenseUnit","source_module":"current_sense.ato",
                "component_roles":[],"interface_pins":[],"nets":[{"name":"PRI","domain":"primary","role":"transformer_primary","required_copper":false},{"name":"SEC","domain":"secondary","role":"sense","required_copper":false}],
                "electrical":{"formula_revision":"owner-pending","rail_voltage_v":{"min":3.3,"max":3.3},"ct_ratio":{"min":100.0,"max":100.0},"input_current_peak_a":{"min":0.0,"max":1.0},"ocp_threshold_current_a":{"min":45.0,"max":55.0},"burden_resistance_ohm":{"min":1.5,"max":1.5},"bias_top_ohm":{"min":47000.0,"max":47000.0},"bias_bottom_ohm":{"min":47000.0,"max":47000.0},"threshold_high_top_ohm":{"min":3740.0,"max":3740.0},"threshold_high_bottom_ohm":{"min":10000.0,"max":10000.0},"threshold_low_top_ohm":{"min":10000.0,"max":10000.0},"threshold_low_bottom_ohm":{"min":3740.0,"max":3740.0},"sensed_current_reference_a":88.0,"source_frequency_hz":{"min":20000.0,"max":100000.0},"operating_current_peak_a":28.76,"operating_frequency_hz":47000.0,"response_limit_us":1.0},
                "geometry":{"copper_layers":2,"clearance_mm":0.2,"primary_secondary_clearance_mm":1.0,"min_trace_width_mm":0.2,"locality_mm":3.0,"primary_nets":["PRI"],"secondary_nets":["SEC"],"required_routed_nets":[]},
                "applicability":[{"topic":"magnetic_dynamics","status":"unsupported","evidence":"not modeled"}]
            },
            "native":{"board_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","extractor_sha256":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","copper_layer_count":2,"components":[
                {"id":"p","mpn":"P","kind":"pad","position_mm":[0.0,0.0],"footprint_pads":[{"pad":"1","net":"PRI","position_mm":[0.0,0.0],"size_mm":[0.2,0.2],"layers":["F.Cu"]}]},
                {"id":"s","mpn":"S","kind":"pad","position_mm":[0.4,0.0],"footprint_pads":[{"pad":"1","net":"SEC","position_mm":[0.4,0.0],"size_mm":[0.2,0.2],"layers":["F.Cu"]}]}
            ],"connections":[],"connectivity_clusters":[],"traces":[],"vias":[],"zones":[]},
            "identity":{"source_manifest_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","profile_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","native_export_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","model_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","board_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","extractor_sha256":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"},
            "source_manifest_utf8":"{}","profile_utf8":"{}","native_export_utf8":"{}","model_utf8":"{}","model":{},"source_components":[],"source_bindings":[]
        })).expect("current-sense test input parses")
    }

    #[test]
    fn primary_secondary_pad_clearance_is_measured_from_native_geometry() {
        let report = validate(&input_with_close_primary_secondary_pads());
        assert!(report.findings.iter().any(|finding| {
            finding.rule == RULE_SEPARATION && finding.status == zapote_core::Status::Fail
        }));
    }

    #[test]
    fn primary_secondary_separation_checks_cross_layer_xy() {
        let mut input = input_with_close_primary_secondary_pads();
        input.native.components[0].footprint_pads[0].layers = vec!["F.Cu".into()];
        input.native.components[1].footprint_pads[0].layers = vec!["B.Cu".into()];
        let report = validate(&input);
        assert!(report.findings.iter().any(|finding| {
            finding.rule == RULE_SEPARATION && finding.status == zapote_core::Status::Fail
        }));
    }

    #[test]
    fn pad_rotation_uses_kicad_clockwise_child_transform() {
        let pad = Pad {
            pad: "1".into(),
            net: "N".into(),
            position_mm: [0.0, 0.0],
            size_mm: [4.0, 1.0],
            drill_mm: [0.0, 0.0],
            shape: 1,
            roundrect_ratio: None,
            layers: vec!["F.Cu".into()],
            orientation_deg: 30.0,
        };
        let corners = pad_corners(&pad);
        // R(-30°) maps local (-2,-0.5) to world (-2.0, +0.567).
        assert!((corners[0][1] - 0.5669873).abs() < 1e-6);
    }

    #[test]
    fn trace_via_crossing_is_checked_as_a_native_pair() {
        let mut input = input_with_close_primary_secondary_pads();
        input.native.components.clear();
        input.native.traces = vec![Trace {
            id: "primary-trace".into(),
            net: "PRI".into(),
            points_mm: vec![[-2.0, 0.0], [2.0, 0.0]],
            layer: "F.Cu".into(),
            width_mm: 0.2,
        }];
        input.native.vias = vec![zapote_core::Via {
            id: "secondary-via".into(),
            net: "SEC".into(),
            position_mm: [0.0, 0.0],
            from_layer: "F.Cu".into(),
            to_layer: "B.Cu".into(),
            diameter_mm: 0.6,
            drill_mm: 0.3,
        }];
        let report = validate(&input);
        assert!(report.findings.iter().any(|finding| {
            finding.rule == RULE_CLEARANCE
                && finding.object == "primary-trace / secondary-via"
                && finding.status == zapote_core::Status::Fail
        }));
    }

    #[test]
    fn zone_crossing_is_detected_without_a_vertex_inside() {
        let mut input = input_with_close_primary_secondary_pads();
        input.native.components.clear();
        input.profile.geometry.primary_nets.clear();
        input.profile.geometry.secondary_nets.clear();
        input.native.zones = vec![zapote_core::NativeZone {
            id: "secondary-pour".into(),
            net: "SEC".into(),
            layer: "F.Cu".into(),
            filled_polygons: vec![zapote_core::NativeFilledPolygon {
                outer_mm: vec![[-1.0, -1.0], [1.0, -1.0], [1.0, 1.0], [-1.0, 1.0]],
                holes_mm: vec![],
            }],
        }];
        input.native.traces = vec![Trace {
            id: "primary-crossing".into(),
            net: "PRI".into(),
            points_mm: vec![[-2.0, 0.0], [2.0, 0.0]],
            layer: "F.Cu".into(),
            width_mm: 0.2,
        }];
        let report = validate(&input);
        assert!(report.findings.iter().any(|finding| {
            finding.rule == RULE_CLEARANCE
                && finding.object == "primary-crossing / secondary-pour"
                && finding.status == zapote_core::Status::Fail
        }));
    }

    #[test]
    fn trace_entirely_in_zone_hole_is_not_treated_as_filled_copper() {
        let mut input = input_with_close_primary_secondary_pads();
        input.native.components.clear();
        input.profile.geometry.primary_nets.clear();
        input.profile.geometry.secondary_nets.clear();
        input.native.zones = vec![zapote_core::NativeZone {
            id: "secondary-pour".into(),
            net: "SEC".into(),
            layer: "F.Cu".into(),
            filled_polygons: vec![zapote_core::NativeFilledPolygon {
                outer_mm: vec![[-5.0, -5.0], [5.0, -5.0], [5.0, 5.0], [-5.0, 5.0]],
                holes_mm: vec![vec![[-1.0, -1.0], [1.0, -1.0], [1.0, 1.0], [-1.0, 1.0]]],
            }],
        }];
        input.native.traces = vec![Trace {
            id: "primary-hole-route".into(),
            net: "PRI".into(),
            points_mm: vec![[-0.5, 0.0], [0.5, 0.0]],
            layer: "F.Cu".into(),
            width_mm: 0.2,
        }];
        let report = validate(&input);
        assert!(!report.findings.iter().any(|finding| {
            finding.rule == RULE_CLEARANCE
                && finding.object == "primary-hole-route / secondary-pour"
                && finding.status == zapote_core::Status::Fail
        }));
    }
}
