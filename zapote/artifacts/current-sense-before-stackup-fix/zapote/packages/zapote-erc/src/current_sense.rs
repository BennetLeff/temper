//! ERC and source/model checks for the standalone current-sensing unit.

use std::collections::{BTreeMap, BTreeSet};
use zapote_core::current_sense::{CurrentSenseInput, NumericRange};
use zapote_core::{CheckReport, Finding};

const RULE_INPUT: &str = "ERC.CURRENT_SENSE.INPUT";
const RULE_COMPONENTS: &str = "ERC.CURRENT_SENSE.COMPONENT_ROLES";
const RULE_INTERFACES: &str = "ERC.CURRENT_SENSE.INTERFACES";
const RULE_CONNECTIVITY: &str = "ERC.CURRENT_SENSE.NATIVE_CONNECTIVITY";
const RULE_MODEL: &str = "ERC.CURRENT_SENSE.ELECTRICAL_MODEL";
const RULE_APPLICABILITY: &str = "ERC.CURRENT_SENSE.APPLICABILITY";

pub fn validate(input: &CurrentSenseInput) -> CheckReport {
    let mut findings = Vec::new();
    let mut gaps = Vec::new();
    let mut checked = vec![
        RULE_INPUT.into(),
        RULE_COMPONENTS.into(),
        RULE_INTERFACES.into(),
        RULE_CONNECTIVITY.into(),
        RULE_MODEL.into(),
        RULE_APPLICABILITY.into(),
    ];
    for error in input.validate() {
        findings.push(Finding::fail(RULE_INPUT, error, "current-sense-input"));
    }
    check_component_roles(input, &mut findings);
    check_interfaces(input, &mut findings);
    check_connectivity(input, &mut findings);
    check_electrical_model(input, &mut findings);
    check_applicability(input, &mut findings, &mut gaps);
    checked.sort();
    checked.dedup();
    CheckReport::from_findings(findings, checked, gaps)
}

fn check_component_roles(input: &CurrentSenseInput, findings: &mut Vec<Finding>) {
    let mut seen_instances = BTreeSet::new();
    for role in &input.profile.component_roles {
        if !seen_instances.insert(role.instance_id.as_str()) {
            findings.push(Finding::fail(
                RULE_COMPONENTS,
                "component instance is assigned to multiple roles",
                role.instance_id.clone(),
            ));
        }
        let Some(component) = input
            .native
            .components
            .iter()
            .find(|c| c.id == role.instance_id)
        else {
            findings.push(Finding::fail(
                RULE_COMPONENTS,
                format!("source role {} has no native component", role.role),
                role.instance_id.clone(),
            ));
            continue;
        };
        if component.mpn != role.mpn {
            findings.push(Finding::fail(
                RULE_COMPONENTS,
                format!(
                    "native MPN {} disagrees with source MPN {}",
                    component.mpn, role.mpn
                ),
                role.instance_id.clone(),
            ));
        }
    }
    let expected: BTreeSet<_> = input
        .profile
        .component_roles
        .iter()
        .map(|role| role.instance_id.as_str())
        .collect();
    for component in &input.native.components {
        if !expected.contains(component.id.as_str()) {
            findings.push(Finding::fail(
                RULE_COMPONENTS,
                "native component is absent from the source role census",
                component.id.clone(),
            ));
        }
    }
}

fn check_interfaces(input: &CurrentSenseInput, findings: &mut Vec<Finding>) {
    let mut seen = BTreeSet::new();
    for interface in &input.profile.interface_pins {
        if !seen.insert(interface.name.as_str()) {
            findings.push(Finding::fail(
                RULE_INTERFACES,
                "interface pin name is duplicated",
                interface.name.clone(),
            ));
        }
        let endpoint_count = input
            .native
            .connections
            .iter()
            .filter(|connection| {
                connection.component == interface.component
                    && connection.pin == interface.pin
                    && connection.net == interface.net
            })
            .count();
        if endpoint_count != 1 {
            findings.push(Finding::fail(
                RULE_INTERFACES,
                format!(
                    "interface {} expects {}.{} -> {}, observed {} matching native connections",
                    interface.name,
                    interface.component,
                    interface.pin,
                    interface.net,
                    endpoint_count
                ),
                format!("{}.{}", interface.component, interface.pin),
            ));
        }
    }
}

fn check_connectivity(input: &CurrentSenseInput, findings: &mut Vec<Finding>) {
    let mut endpoints_by_net: BTreeMap<&str, Vec<String>> = BTreeMap::new();
    for binding in &input.source_bindings {
        endpoints_by_net
            .entry(binding.net.as_str())
            .or_default()
            .push(format!("{}.{}", binding.instance_id, binding.pad));
    }
    for net in &input.profile.nets {
        let Some(endpoints) = endpoints_by_net.get(net.name.as_str()) else {
            findings.push(Finding::fail(
                RULE_CONNECTIVITY,
                "source net has no physical pad endpoint",
                net.name.clone(),
            ));
            continue;
        };
        let clusters: Vec<_> = input
            .native
            .connectivity_clusters
            .iter()
            .filter(|cluster| cluster.net == net.name)
            .collect();
        if clusters.is_empty() {
            findings.push(Finding::fail(
                RULE_CONNECTIVITY,
                "native evidence has no connectivity cluster for source net",
                net.name.clone(),
            ));
            continue;
        }
        let containing: Vec<_> = clusters
            .iter()
            .filter(|cluster| {
                endpoints
                    .iter()
                    .all(|endpoint| cluster.nodes.contains(endpoint))
            })
            .collect();
        if containing.is_empty() {
            findings.push(Finding::fail(
                RULE_CONNECTIVITY,
                "source endpoints are split across native copper clusters",
                net.name.clone(),
            ));
        }
        if net.required_copper && !has_physical_copper(input, &net.name) {
            findings.push(Finding::fail(
                RULE_CONNECTIVITY,
                "net is marked required_copper but native traces, vias, and filled zones are absent",
                net.name.clone(),
            ));
        }
    }
}

fn has_physical_copper(input: &CurrentSenseInput, net: &str) -> bool {
    input.native.traces.iter().any(|trace| trace.net == net)
        || input.native.vias.iter().any(|via| via.net == net)
        || input
            .native
            .zones
            .iter()
            .any(|zone| zone.net == net && !zone.filled_polygons.is_empty())
}

fn divider(vcc: f64, top: f64, bottom: f64) -> f64 {
    vcc * bottom / (top + bottom)
}

fn corner(value: &zapote_core::current_sense::NumericRange, high: bool) -> f64 {
    if high {
        value.max
    } else {
        value.min
    }
}

/// Recompute the owner-supplied CST3015/1:100 floating-burden topology.  The
/// divider and burden values are source-bound profile inputs; no RTD or
/// producer claim is treated as an input voltage or threshold formula.
pub fn recompute_electrical_claims(input: &CurrentSenseInput) -> BTreeMap<String, f64> {
    let e = &input.profile.electrical;
    let nominal = |positive: bool| {
        let vcc = (e.rail_voltage_v.min + e.rail_voltage_v.max) / 2.0;
        let bias = divider(
            vcc,
            (e.bias_top_ohm.min + e.bias_top_ohm.max) / 2.0,
            (e.bias_bottom_ohm.min + e.bias_bottom_ohm.max) / 2.0,
        );
        let reference = if positive {
            divider(
                vcc,
                (e.threshold_high_top_ohm.min + e.threshold_high_top_ohm.max) / 2.0,
                (e.threshold_high_bottom_ohm.min + e.threshold_high_bottom_ohm.max) / 2.0,
            )
        } else {
            divider(
                vcc,
                (e.threshold_low_top_ohm.min + e.threshold_low_top_ohm.max) / 2.0,
                (e.threshold_low_bottom_ohm.min + e.threshold_low_bottom_ohm.max) / 2.0,
            )
        };
        (if positive {
            reference - bias
        } else {
            bias - reference
        }) * ((e.ct_ratio.min + e.ct_ratio.max) / 2.0)
            / ((e.burden_resistance_ohm.min + e.burden_resistance_ohm.max) / 2.0)
    };
    let mut corners = Vec::with_capacity(32768);
    // Sixteen independent corners: the final bit is the sourced 1% series
    // resistor tolerance, in addition to rail, resistor, loading, and offset
    // bounds.  Omitting it would let the model understate the real envelope.
    for mask in 0u32..65536 {
        let vcc = corner(&e.rail_voltage_v, mask & 128 != 0);
        let burden = corner(&e.burden_resistance_ohm, mask & 1 != 0);
        let bias_top = corner(&e.bias_top_ohm, mask & 2 != 0);
        let bias_bottom = corner(&e.bias_bottom_ohm, mask & 4 != 0);
        let hi_top = corner(&e.threshold_high_top_ohm, mask & 8 != 0);
        let hi_bottom = corner(&e.threshold_high_bottom_ohm, mask & 16 != 0);
        let lo_top = corner(&e.threshold_low_top_ohm, mask & 32 != 0);
        let lo_bottom = corner(&e.threshold_low_bottom_ohm, mask & 64 != 0);
        let clamp_leakage = corner(&e.clamp_leakage_a, mask & 256 != 0);
        let host_load = corner(&e.host_monitor_load_a, mask & 512 != 0);
        let sense_bias = corner(&e.sense_input_bias_a, mask & 1024 != 0);
        let hi_bias = corner(&e.threshold_input_bias_a, mask & 2048 != 0);
        let lo_bias = corner(&e.threshold_input_bias_a, mask & 4096 != 0);
        let positive_offset = corner(&e.comparator_positive_offset_v, mask & 8192 != 0);
        let negative_offset = corner(&e.comparator_negative_offset_v, mask & 16384 != 0);
        let sense_series = corner(&e.sense_series_resistance_ohm, mask & 32768 != 0);
        let source_load = clamp_leakage + host_load + sense_bias;
        let bias = divider(vcc, bias_top, bias_bottom)
            - source_load * (bias_top * bias_bottom / (bias_top + bias_bottom));
        let hi =
            divider(vcc, hi_top, hi_bottom) - hi_bias * (hi_top * hi_bottom / (hi_top + hi_bottom));
        let lo =
            divider(vcc, lo_top, lo_bottom) - lo_bias * (lo_top * lo_bottom / (lo_top + lo_bottom));
        let ratio = (e.ct_ratio.min + e.ct_ratio.max) / 2.0;
        // KCL sign convention: a positive load on SENSE_MON lowers the
        // loaded bias by I*Rth, while its drop through the series resistor and
        // burden enters the comparator polarity with the opposite sign.  The
        // latter term therefore adds for the positive comparator and subtracts
        // for the negative comparator.  Keeping these signs explicit prevents
        // a producer midpoint annotation from hiding a reversed source path.
        let sense_offset = source_load * (sense_series + burden);
        corners.push((
            (hi - bias + sense_offset - positive_offset) * ratio / burden,
            (bias - lo - sense_offset + negative_offset) * ratio / burden,
        ));
    }
    let positive_min = corners.iter().map(|v| v.0).fold(f64::INFINITY, f64::min);
    let positive_max = corners
        .iter()
        .map(|v| v.0)
        .fold(f64::NEG_INFINITY, f64::max);
    let negative_min = corners.iter().map(|v| v.1).fold(f64::INFINITY, f64::min);
    let negative_max = corners
        .iter()
        .map(|v| v.1)
        .fold(f64::NEG_INFINITY, f64::max);
    let reference = e.sensed_current_reference_a;
    let burden = (e.burden_resistance_ohm.min + e.burden_resistance_ohm.max) / 2.0;
    BTreeMap::from([
        ("nominal_trip_a_positive".into(), nominal(true)),
        ("nominal_trip_a_negative".into(), nominal(false)),
        ("corner_trip_a_min".into(), positive_min.min(negative_min)),
        ("corner_trip_a_max".into(), positive_max.max(negative_max)),
        ("corner_trip_a_positive_min".into(), positive_min),
        ("corner_trip_a_positive_max".into(), positive_max),
        ("corner_trip_a_negative_min".into(), negative_min),
        ("corner_trip_a_negative_max".into(), negative_max),
        (
            "sense_voltage_at_reference_a_positive".into(),
            (e.rail_voltage_v.min + e.rail_voltage_v.max) / 4.0
                + reference * burden / ((e.ct_ratio.min + e.ct_ratio.max) / 2.0),
        ),
        (
            "sense_voltage_at_reference_a_negative".into(),
            (e.rail_voltage_v.min + e.rail_voltage_v.max) / 4.0
                - reference * burden / ((e.ct_ratio.min + e.ct_ratio.max) / 2.0),
        ),
        (
            "burden_power_at_operating_point_w".into(),
            (e.operating_current_peak_a
                / ((e.ct_ratio.min + e.ct_ratio.max) / 2.0)
                / 2.0_f64.sqrt())
            .powi(2)
                * burden,
        ),
    ])
}

fn check_electrical_model(input: &CurrentSenseInput, findings: &mut Vec<Finding>) {
    let model_object = input.model.as_object();
    let model_revision = input
        .model
        .get("formula_revision")
        .or_else(|| input.model.get("schema"))
        .and_then(|value| value.as_str());
    if model_revision != Some(input.profile.electrical.formula_revision.as_str()) {
        findings.push(Finding::fail(
            RULE_MODEL,
            "model formula_revision does not match the source profile",
            "model.formula_revision",
        ));
    }
    for (name, expected) in recompute_electrical_claims(input) {
        let actual = model_claim_value(model_object, &name);
        if actual.is_none_or(|value| !value.is_finite() || !close(value, expected)) {
            findings.push(Finding::fail(
                RULE_MODEL,
                format!("model claim {name} does not match Rust recomputation ({expected:.9})"),
                format!("model.{name}"),
            ));
        }
    }
    let expected = recompute_electrical_claims(input);
    if let Some(limit) = input.profile.electrical.burden_power_limit_w {
        if expected["burden_power_at_operating_point_w"] > limit {
            findings.push(Finding::fail(
                RULE_MODEL,
                format!("recomputed burden power exceeds source limit {limit:.9} W"),
                "electrical.burden_power_limit_w",
            ));
        }
    }
    let both_polarities = model_object
        .and_then(|object| {
            object
                .get("both_polarities_modeled")
                .or_else(|| object.get("verdicts")?.get("both_polarities_modeled"))
        })
        .and_then(|v| v.as_bool());
    if both_polarities != Some(true) {
        findings.push(Finding::fail(
            RULE_MODEL,
            "owner model must model both comparator polarities",
            "model.both_polarities_modeled",
        ));
    }
    let trip_corners_in_window = model_object
        .and_then(|object| {
            object
                .get("trip_corners_in_window")
                .or_else(|| object.get("verdicts")?.get("trip_corners_in_window"))
        })
        .and_then(|v| v.as_bool());
    if trip_corners_in_window != Some(true)
        || expected["corner_trip_a_min"] < 45.0
        || expected["corner_trip_a_max"] > 55.0
    {
        findings.push(Finding::fail(
            RULE_MODEL,
            "recomputed CST3015 divider corners are outside fixed 45..55 Apeak",
            "model.trip_corners_in_window",
        ));
    }
}

fn check_applicability(
    input: &CurrentSenseInput,
    findings: &mut Vec<Finding>,
    gaps: &mut Vec<String>,
) {
    for statement in &input.profile.applicability {
        if !matches!(statement.status.as_str(), "qualified" | "not_applicable") {
            let message = format!(
                "{} applicability is {}{}",
                statement.topic,
                statement.status,
                if statement.evidence.is_empty() {
                    String::new()
                } else {
                    format!(": {}", statement.evidence)
                }
            );
            findings.push(Finding::indeterminate(
                RULE_APPLICABILITY,
                message.clone(),
                statement.topic.clone(),
            ));
            gaps.push(message);
        }
    }
    if input
        .profile
        .applicability
        .iter()
        .all(|statement| statement.evidence.is_empty())
    {
        findings.push(Finding::indeterminate(
            RULE_APPLICABILITY,
            "applicability statuses contain no supporting evidence; hardware qualification is not established",
            "current-sense-profile",
        ));
        gaps.push("current-sense applicability evidence is absent".into());
    }
}

fn close(actual: f64, expected: f64) -> bool {
    let scale = actual.abs().max(expected.abs()).max(1.0);
    (actual - expected).abs() <= 1e-7 * scale
}

fn model_claim_value(
    model: Option<&serde_json::Map<String, serde_json::Value>>,
    name: &str,
) -> Option<f64> {
    let object = model?;
    if let Some(value) = object
        .get("electrical_claims")
        .and_then(|claims| claims.get(name))
        .and_then(serde_json::Value::as_f64)
    {
        return Some(value);
    }
    let (section, key) = match name {
        "nominal_trip_a_positive" => ("nominal_trip_a", "positive"),
        "nominal_trip_a_negative" => ("nominal_trip_a", "negative"),
        "corner_trip_a_min" => ("corner_trip_a", "min"),
        "corner_trip_a_max" => ("corner_trip_a", "max"),
        "corner_trip_a_positive_min" => ("corner_trip_a", "positive_min"),
        "corner_trip_a_positive_max" => ("corner_trip_a", "positive_max"),
        "corner_trip_a_negative_min" => ("corner_trip_a", "negative_min"),
        "corner_trip_a_negative_max" => ("corner_trip_a", "negative_max"),
        "sense_voltage_at_reference_a_positive" => ("sense_voltage_at_88a_v", "positive"),
        "sense_voltage_at_reference_a_negative" => ("sense_voltage_at_88a_v", "negative"),
        "burden_power_at_operating_point_w" => ("burden_power_at_28_76a_peak_w", ""),
        _ => return object.get(name).and_then(serde_json::Value::as_f64),
    };
    if key.is_empty() {
        object.get(section).and_then(serde_json::Value::as_f64)
    } else {
        object
            .get(section)?
            .get(key)
            .and_then(serde_json::Value::as_f64)
    }
}

#[allow(dead_code)]
fn valid_range(range: &NumericRange) -> bool {
    range.is_valid()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn recomputation_uses_profile_values_without_rtd_constants() {
        let profile: zapote_core::current_sense::CurrentSenseProfile = serde_json::from_value(serde_json::json!({
            "schema":"zapote.current-sense.profile.v1","profile_id":"CurrentSenseUnit","source_module":"src/current_sense.ato",
            "component_roles":[],"interface_pins":[],"nets":[],
            "electrical":{"formula_revision":"test-v1","rail_voltage_v":{"min":3.3,"max":3.3},"ct_ratio":{"min":100.0,"max":100.0},"input_current_peak_a":{"min":10.0,"max":20.0},"ocp_threshold_current_a":{"min":45.0,"max":55.0},"burden_resistance_ohm":{"min":0.1,"max":0.2},"bias_top_ohm":{"min":47000.0,"max":47000.0},"bias_bottom_ohm":{"min":47000.0,"max":47000.0},"threshold_high_top_ohm":{"min":3740.0,"max":3740.0},"threshold_high_bottom_ohm":{"min":10000.0,"max":10000.0},"threshold_low_top_ohm":{"min":10000.0,"max":10000.0},"threshold_low_bottom_ohm":{"min":3740.0,"max":3740.0},"sensed_current_reference_a":88.0,"source_frequency_hz":{"min":20000.0,"max":100000.0},"operating_current_peak_a":28.76,"operating_frequency_hz":47000.0,"response_limit_us":1.0},
            "geometry":{"copper_layers":2,"clearance_mm":0.2,"primary_secondary_clearance_mm":1.0,"min_trace_width_mm":0.2,"locality_mm":3.0,"primary_nets":["PRI"],"secondary_nets":["SEC"]},
            "applicability":[{"topic":"magnetic_dynamics","status":"unsupported","evidence":"not modeled"}]
        })).expect("profile parses");
        let input: CurrentSenseInput = serde_json::from_value(serde_json::json!({"schema":"zapote.current-sense.input.v1","profile":profile,"native":{"board_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","extractor_sha256":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","copper_layer_count":2,"components":[],"connections":[],"connectivity_clusters":[],"traces":[],"vias":[],"zones":[]},"identity":{"source_manifest_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","profile_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","native_export_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","model_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","board_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","extractor_sha256":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"},"source_manifest_utf8":"{}","profile_utf8":"{}","native_export_utf8":"{}","model_utf8":"{}","model":{},"source_components":[],"source_bindings":[]})).expect("input parses");
        assert!(recompute_electrical_claims(&input)["corner_trip_a_min"] > 20.0);
    }

    #[test]
    fn missing_independent_electrical_claims_fail_closed() {
        let profile: zapote_core::current_sense::CurrentSenseProfile =
            serde_json::from_value(serde_json::json!({
                "schema":"zapote.current-sense.profile.v1","profile_id":"CurrentSenseUnit","source_module":"current_sense.ato",
                "component_roles":[],"interface_pins":[],"nets":[],
                "electrical":{"formula_revision":"owner-pending","rail_voltage_v":{"min":3.3,"max":3.3},"ct_ratio":{"min":100.0,"max":100.0},"input_current_peak_a":{"min":0.0,"max":1.0},"ocp_threshold_current_a":{"min":45.0,"max":55.0},"burden_resistance_ohm":{"min":1.0,"max":1.0},"bias_top_ohm":{"min":47000.0,"max":47000.0},"bias_bottom_ohm":{"min":47000.0,"max":47000.0},"threshold_high_top_ohm":{"min":3740.0,"max":3740.0},"threshold_high_bottom_ohm":{"min":10000.0,"max":10000.0},"threshold_low_top_ohm":{"min":10000.0,"max":10000.0},"threshold_low_bottom_ohm":{"min":3740.0,"max":3740.0},"sensed_current_reference_a":88.0,"source_frequency_hz":{"min":20000.0,"max":100000.0},"operating_current_peak_a":28.76,"operating_frequency_hz":47000.0,"response_limit_us":1.0},
                "geometry":{"copper_layers":2,"clearance_mm":0.2,"primary_secondary_clearance_mm":1.0,"min_trace_width_mm":0.2,"locality_mm":3.0,"primary_nets":["PRI"],"secondary_nets":["SEC"]},"applicability":[{"topic":"device_limits","status":"unsupported","evidence":"owner pending"}]
            })).expect("profile parses");
        let input: CurrentSenseInput = serde_json::from_value(serde_json::json!({
            "schema":"zapote.current-sense.input.v1","profile":profile,
            "native":{"board_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","extractor_sha256":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","copper_layer_count":2,"components":[],"connections":[],"connectivity_clusters":[],"traces":[],"vias":[],"zones":[]},
            "identity":{"source_manifest_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","profile_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","native_export_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","model_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","board_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","extractor_sha256":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"},"source_manifest_utf8":"{}","profile_utf8":"{}","native_export_utf8":"{}","model_utf8":"{}","model":{},"source_components":[],"source_bindings":[]
        })).expect("input parses");
        let report = validate(&input);
        assert!(report.findings.iter().any(
            |finding| finding.rule == RULE_MODEL && finding.status == zapote_core::Status::Fail
        ));
        assert!(report
            .findings
            .iter()
            .any(|finding| finding.rule == RULE_APPLICABILITY
                && finding.status == zapote_core::Status::Indeterminate));
    }

    #[test]
    fn owner_model_fixture_matches_floating_burden_topology() {
        let profile: zapote_core::current_sense::CurrentSenseProfile = serde_json::from_value(serde_json::json!({
            "schema":"zapote.current-sense.profile.v1","profile_id":"standalone_primary_current_sense","source_module":"current_sense_unit.ato","component_roles":[],"interface_pins":[],"nets":[],
            "electrical":{"formula_revision":"current_sense_unit_model.v3","rail_voltage_v":{"min":3.135,"max":3.465},"ct_ratio":{"min":100.0,"max":100.0},"input_current_peak_a":{"min":0.0,"max":88.0},"ocp_threshold_current_a":{"min":45.0,"max":55.0},"burden_resistance_ohm":{"min":1.485,"max":1.515},"bias_top_ohm":{"min":999.0,"max":1001.0},"bias_bottom_ohm":{"min":999.0,"max":1001.0},"threshold_high_top_ohm":{"min":3736.26,"max":3743.74},"threshold_high_bottom_ohm":{"min":9990.0,"max":10010.0},"threshold_low_top_ohm":{"min":9990.0,"max":10010.0},"threshold_low_bottom_ohm":{"min":3736.26,"max":3743.74},"clamp_leakage_a":{"min":-0.000004,"max":0.000004},"sense_input_bias_a":{"min":-0.00000001,"max":0.00000001},"threshold_input_bias_a":{"min":-0.000000005,"max":0.000000005},"sense_series_resistance_ohm":{"min":1000.0,"max":1000.0},"host_monitor_load_a":{"min":-0.00000035,"max":0.00000035},"comparator_positive_offset_v":{"min":-0.004,"max":0.004},"comparator_negative_offset_v":{"min":-0.004,"max":0.004},"sensed_current_reference_a":88.0,"source_frequency_hz":{"min":780.0,"max":1000000.0},"operating_current_peak_a":28.76,"operating_frequency_hz":47000.0,"response_limit_us":1.0},
            "geometry":{"copper_layers":2,"clearance_mm":0.2,"primary_secondary_clearance_mm":12.6,"min_trace_width_mm":0.2,"locality_mm":3.0,"primary_nets":["PRIMARY"],"secondary_nets":["GND"]},"applicability":[{"topic":"timing","status":"unsupported","evidence":"model does not claim end-to-end latch timing"}],"source_value_bindings":[{"instance_id":"sense.burden","attribute":"value","value":"1.50ohm"}]
        })).expect("owner profile parses");
        let mut input: CurrentSenseInput = serde_json::from_value(serde_json::json!({"schema":"zapote.current-sense.input.v1","profile":profile,"native":{"board_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","extractor_sha256":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","copper_layer_count":2,"components":[],"connections":[],"connectivity_clusters":[],"traces":[],"vias":[],"zones":[]},"identity":{"source_manifest_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","profile_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","native_export_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","model_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","board_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","extractor_sha256":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"},"source_manifest_utf8":"{}","profile_utf8":"{}","native_export_utf8":"{}","model_utf8":"{}","model":{},"source_components":[],"source_bindings":[]})).expect("owner input parses");
        let claims = recompute_electrical_claims(&input);
        assert!(close(claims["nominal_trip_a_positive"], 50.116448326));
        assert!(close(claims["nominal_trip_a_negative"], 50.116448326));
        assert!((45.0..=55.0).contains(&claims["corner_trip_a_min"]));
        assert!((45.0..=55.0).contains(&claims["corner_trip_a_max"]));
        assert!(close(claims["sense_voltage_at_reference_a_positive"], 2.97));
        assert!(close(
            claims["burden_power_at_operating_point_w"],
            0.062035320
        ));

        // Directional KCL regression: a positive SENSE_MON load lowers the
        // loaded bias through Rth, then contributes the opposite signed drop
        // through Rseries+Rb at the two comparator inputs.
        input.profile.electrical.host_monitor_load_a = NumericRange::default();
        input.profile.electrical.sense_input_bias_a = NumericRange::default();
        input.profile.electrical.clamp_leakage_a = NumericRange::default();
        let unloaded = recompute_electrical_claims(&input);
        let nominal_positive_min = unloaded["corner_trip_a_positive_min"];
        let nominal_negative_min = unloaded["corner_trip_a_negative_min"];
        input.profile.electrical.clamp_leakage_a = NumericRange {
            min: 4e-6,
            max: 4e-6,
        };
        let loaded = recompute_electrical_claims(&input);
        assert!(loaded["corner_trip_a_positive_min"] > nominal_positive_min);
        assert!(loaded["corner_trip_a_negative_min"] < nominal_negative_min);
    }
}
