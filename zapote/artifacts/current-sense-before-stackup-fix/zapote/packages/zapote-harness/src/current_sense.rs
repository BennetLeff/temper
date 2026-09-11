//! Thin composition boundary for the standalone CurrentSenseUnit validators.

use sha2::{Digest, Sha256};
use zapote_core::current_sense::{
    ApplicabilityStatement, CurrentSenseComponentRole, CurrentSenseElectricalProfile,
    CurrentSenseGeometry, CurrentSenseIdentity, CurrentSenseInput, CurrentSenseInterfacePin,
    CurrentSenseNet, CurrentSenseProfile, NumericRange, SourceValueBinding,
};
use zapote_core::unit::UnitNativeEvidence;
use zapote_core::{CheckReport, Finding, Status};

/// Execute all registered current-sense rules against one source/native input.
/// The harness owns composition only; engineering policy remains in ERC/DRC.
pub fn run_current_sense(input: &CurrentSenseInput) -> CheckReport {
    // The owner artifact is a different schema from the normalized transport.
    // Rebuild its entire projection so edited limits, interfaces or empty
    // geometry populations cannot retain the original owner's identity.
    if serde_json::from_str::<serde_json::Value>(&input.profile_utf8)
        .ok()
        .is_some_and(|value| value["schema"] == "zapote.current_sense_profile.v1")
    {
        let projection = build_current_sense_input(
            input.source_manifest_utf8.clone(),
            input.profile_utf8.clone(),
            input.native_export_utf8.clone(),
            input.model_utf8.clone(),
        );
        let matches = projection.as_ref().is_ok_and(|expected| {
            serde_json::to_value(&expected.profile).ok()
                == serde_json::to_value(&input.profile).ok()
        });
        if !matches {
            return CheckReport::from_findings(
                vec![Finding::fail(
                    "ERC.CURRENT_SENSE.INPUT",
                    "normalized profile differs from the source/owner artifact projection",
                    "profile",
                )],
                vec!["ERC.CURRENT_SENSE.INPUT".into()],
                Vec::new(),
            );
        }
    }
    let erc = zapote_erc::current_sense::validate(input);
    let drc = zapote_drc::current_sense::validate(input);
    let mut findings: Vec<Finding> = erc
        .findings
        .iter()
        .chain(drc.findings.iter())
        .cloned()
        .collect();
    let mut checked = erc
        .checked_rules
        .iter()
        .chain(drc.checked_rules.iter())
        .cloned()
        .collect::<Vec<_>>();
    checked.sort();
    checked.dedup();
    let mut gaps: Vec<String> = erc
        .coverage_gaps
        .iter()
        .chain(drc.coverage_gaps.iter())
        .cloned()
        .collect::<Vec<_>>();
    // Input errors are emitted by both domain validators. Preserve one clear
    // finding per message while retaining the fail-closed status.
    findings.dedup_by(|first, second| {
        first.rule == second.rule
            && first.object == second.object
            && first.message == second.message
    });
    if findings
        .iter()
        .any(|finding| finding.status == Status::Fail)
    {
        gaps.retain(|gap| !gap.is_empty());
    }
    CheckReport::from_findings(findings, checked, gaps)
}

pub fn parse_current_sense_input(bytes: &[u8]) -> Result<CurrentSenseInput, serde_json::Error> {
    serde_json::from_slice(bytes)
}

fn digest(bytes: &[u8]) -> String {
    Sha256::digest(bytes)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

fn bounded(value: f64, tolerance: f64) -> NumericRange {
    NumericRange {
        min: value * (1.0 - tolerance),
        max: value * (1.0 + tolerance),
    }
}

fn owner_number(owner: &serde_json::Value, path: &[&str]) -> Result<f64, Vec<String>> {
    path.iter()
        .try_fold(owner, |current, key| current.get(*key))
        .and_then(serde_json::Value::as_f64)
        .ok_or_else(|| vec![format!("owner profile missing numeric {}", path.join("."))])
}

fn source_tolerance_fraction(
    attributes: Option<&serde_json::Map<String, serde_json::Value>>,
    instance_id: &str,
) -> Result<f64, Vec<String>> {
    let value = attributes
        .and_then(|items| items.get(instance_id))
        .and_then(|item| item.get("value"))
        .and_then(serde_json::Value::as_str)
        .ok_or_else(|| vec![format!("source attribute {instance_id}.value is required")])?;
    let tolerance = value
        .split_once("+/-")
        .and_then(|(_, suffix)| suffix.trim().strip_suffix('%'))
        .and_then(|percent| percent.trim().parse::<f64>().ok())
        .map(|percent| percent / 100.0)
        .ok_or_else(|| {
            vec![format!(
                "source attribute {instance_id}.value lacks a percentage tolerance"
            )]
        })?;
    if tolerance.is_finite() && tolerance >= 0.0 {
        Ok(tolerance)
    } else {
        Err(vec![format!(
            "source attribute {instance_id}.value has invalid tolerance"
        )])
    }
}

/// Build the normalized validator transport from the actual source compiler,
/// native extractor, owner profile, and owner model artifacts. The profile is
/// a typed projection of the owner JSON; all four original byte streams remain
/// in the input and are hash-bound by `CurrentSenseInput::validate`.
pub fn build_current_sense_input(
    source_manifest_utf8: String,
    profile_utf8: String,
    native_export_utf8: String,
    model_utf8: String,
) -> Result<CurrentSenseInput, Vec<String>> {
    let source_value: serde_json::Value = serde_json::from_str(&source_manifest_utf8)
        .map_err(|error| vec![format!("source manifest is not JSON: {error}")])?;
    let owner: serde_json::Value = serde_json::from_str(&profile_utf8)
        .map_err(|error| vec![format!("owner profile is not JSON: {error}")])?;
    let native: UnitNativeEvidence =
        serde_json::from_str(&native_export_utf8).map_err(|error| {
            vec![format!(
                "native export is not typed native evidence: {error}"
            )]
        })?;
    let model: serde_json::Value = serde_json::from_str(&model_utf8)
        .map_err(|error| vec![format!("model is not JSON: {error}")])?;
    let (source_components, source_bindings) =
        zapote_core::current_sense::source_census_from_manifest(&source_manifest_utf8)?;
    let source_attributes = source_value["source_attributes"].as_object();
    let mut roles = Vec::new();
    for component in &source_components {
        let native_component = native
            .components
            .iter()
            .find(|item| item.id == component.instance_id);
        let attributes = source_attributes.and_then(|items| items.get(&component.instance_id));
        roles.push(CurrentSenseComponentRole {
            role: component.instance_id.clone(),
            instance_id: component.instance_id.clone(),
            mpn: component.mpn.clone(),
            kind: native_component
                .map(|item| item.kind.clone())
                .unwrap_or_default(),
            value: attributes
                .and_then(|item| item["value"].as_str())
                .map(str::to_owned),
        });
    }
    let mut interfaces = Vec::new();
    for connection in &native.connections {
        let name = format!("{}.{}", connection.component, connection.pin);
        if interfaces
            .iter()
            .any(|interface: &CurrentSenseInterfacePin| interface.name == name)
        {
            continue;
        }
        interfaces.push(CurrentSenseInterfacePin {
            name,
            component: connection.component.clone(),
            pin: connection.pin.clone(),
            net: connection.net.clone(),
            direction: "unknown".into(),
        });
    }
    let mut net_names: std::collections::BTreeSet<String> = source_bindings
        .iter()
        .map(|binding| binding.net.clone())
        .collect();
    net_names.extend(
        native
            .components
            .iter()
            .flat_map(|component| component.footprint_pads.iter().map(|pad| pad.net.clone())),
    );
    let nets = net_names
        .iter()
        .map(|name| CurrentSenseNet {
            name: name.clone(),
            domain: if name == "PRIMARY_IN" || name == "PRIMARY_OUT" {
                "primary".into()
            } else {
                "secondary".into()
            },
            role: "source_manifest_net".into(),
            required_copper: source_bindings
                .iter()
                .filter(|binding| &binding.net == name)
                .count()
                > 1,
        })
        .collect();
    let requirements = &owner["requirements"];
    let rail = owner_number(&owner, &["interfaces", "power", "nominal_v"])?;
    let rail_tolerance = owner_number(&owner, &["interfaces", "power", "tolerance_fraction"])?;
    let burden = owner_number(&owner, &["front_end", "burden_ohm"])?;
    let burden_tolerance = owner_number(&owner, &["front_end", "burden_tolerance_fraction"])?;
    let bias_tolerance = owner_number(&owner, &["front_end", "bias_tolerance_fraction"])?;
    let threshold_tolerance = owner_number(&owner, &["front_end", "threshold_tolerance_fraction"])?;
    let source_frequency = requirements["source_frequency_hz"]
        .as_array()
        .filter(|values| values.len() == 2)
        .ok_or_else(|| vec!["owner profile source_frequency_hz is required".into()])?;
    let source_frequency_hz = NumericRange {
        min: source_frequency[0].as_f64().unwrap_or(0.0),
        max: source_frequency[1].as_f64().unwrap_or(0.0),
    };
    let ocp = requirements["ocp_peak_a"]
        .as_array()
        .filter(|values| values.len() == 2)
        .ok_or_else(|| vec!["owner profile ocp_peak_a is required".into()])?;
    let electrical = CurrentSenseElectricalProfile {
        formula_revision: model["schema"]
            .as_str()
            .ok_or_else(|| vec!["owner model schema is required".into()])?
            .into(),
        rail_voltage_v: bounded(rail, rail_tolerance),
        ct_ratio: bounded(
            owner_number(&owner, &["transformer", "ratio_primary_to_secondary"])?,
            0.0,
        ),
        input_current_peak_a: NumericRange {
            min: 0.0,
            max: owner_number(&owner, &["transformer", "sensed_current_reference_a"])?,
        },
        ocp_threshold_current_a: NumericRange {
            min: ocp[0].as_f64().unwrap_or(0.0),
            max: ocp[1].as_f64().unwrap_or(0.0),
        },
        burden_resistance_ohm: bounded(burden, burden_tolerance),
        bias_top_ohm: bounded(
            owner_number(&owner, &["front_end", "bias_top_ohm"])?,
            bias_tolerance,
        ),
        bias_bottom_ohm: bounded(
            owner_number(&owner, &["front_end", "bias_bottom_ohm"])?,
            bias_tolerance,
        ),
        threshold_high_top_ohm: bounded(
            owner_number(&owner, &["front_end", "threshold_high_top_ohm"])?,
            threshold_tolerance,
        ),
        threshold_high_bottom_ohm: bounded(
            owner_number(&owner, &["front_end", "threshold_high_bottom_ohm"])?,
            threshold_tolerance,
        ),
        threshold_low_top_ohm: bounded(
            owner_number(&owner, &["front_end", "threshold_low_top_ohm"])?,
            threshold_tolerance,
        ),
        threshold_low_bottom_ohm: bounded(
            owner_number(&owner, &["front_end", "threshold_low_bottom_ohm"])?,
            threshold_tolerance,
        ),
        clamp_leakage_a: {
            let value = owner_number(
                &owner,
                &["front_end", "clamp_reverse_leakage_total_a_at_25c"],
            )?;
            NumericRange {
                min: -value,
                max: value,
            }
        },
        sense_input_bias_a: {
            let value = owner_number(&owner, &["front_end", "sense_input_bias_combined_a"])?;
            NumericRange {
                min: -value,
                max: value,
            }
        },
        threshold_input_bias_a: {
            let value = owner_number(&owner, &["front_end", "comparator_input_bias_a_per_input"])?;
            NumericRange {
                min: -value,
                max: value,
            }
        },
        sense_series_resistance_ohm: bounded(
            owner_number(&owner, &["front_end", "input_series_ohm"])?,
            source_tolerance_fraction(source_attributes, "r_sense_series")?,
        ),
        host_monitor_load_a: {
            let value = owner_number(&owner, &["front_end", "host_monitor_load_bound_a"])?;
            NumericRange {
                min: -value,
                max: value,
            }
        },
        comparator_positive_offset_v: {
            let value = owner_number(&owner, &["front_end", "effective_comparator_error_bound_v"])?;
            NumericRange {
                min: -value,
                max: value,
            }
        },
        comparator_negative_offset_v: {
            let value = owner_number(&owner, &["front_end", "effective_comparator_error_bound_v"])?;
            NumericRange {
                min: -value,
                max: value,
            }
        },
        sensed_current_reference_a: owner_number(
            &owner,
            &["transformer", "sensed_current_reference_a"],
        )?,
        source_frequency_hz,
        operating_current_peak_a: owner_number(
            &owner,
            &["requirements", "current_operating_point_peak_a"],
        )?,
        operating_frequency_hz: owner_number(
            &owner,
            &["requirements", "current_operating_point_frequency_hz"],
        )?,
        response_limit_us: owner_number(&owner, &["requirements", "complete_chain_response_us"])?,
        burden_power_limit_w: None,
    };
    let quantity_instances = [
        ("burden", "burden_resistance_ohm"),
        ("r_sense_series", "sense_series_resistance_ohm"),
        ("r_sense_series", "sense_series_resistance_ohm"),
        ("r_bias_top", "bias_top_ohm"),
        ("r_bias_bottom", "bias_bottom_ohm"),
        ("r_ref_hi_top", "threshold_high_top_ohm"),
        ("r_ref_hi_bottom", "threshold_high_bottom_ohm"),
        ("r_ref_lo_top", "threshold_low_top_ohm"),
        ("r_ref_lo_bottom", "threshold_low_bottom_ohm"),
    ];
    let source_value_bindings = quantity_instances
        .iter()
        .filter_map(|(instance, quantity)| {
            source_attributes?
                .get(*instance)?
                .get("value")?
                .as_str()
                .map(|value| SourceValueBinding {
                    instance_id: (*instance).into(),
                    attribute: "value".into(),
                    value: value.into(),
                    quantity: (*quantity).into(),
                })
        })
        .collect();
    let applicability = owner["gates"]
        .as_object()
        .into_iter()
        .flatten()
        .map(|(topic, status)| ApplicabilityStatement {
            topic: topic.clone(),
            status: "unsupported".into(),
            evidence: status.as_str().unwrap_or("missing").into(),
        })
        .collect();
    let profile = CurrentSenseProfile {
        schema: zapote_core::current_sense::PROFILE_SCHEMA.into(),
        profile_id: owner["unit"]
            .as_str()
            .unwrap_or("standalone_primary_current_sense")
            .into(),
        source_module: owner["source"]
            .as_str()
            .unwrap_or("elec/src/current_sense_unit.ato")
            .into(),
        component_roles: roles,
        interface_pins: interfaces,
        nets,
        electrical,
        geometry: CurrentSenseGeometry {
            copper_layers: 2,
            clearance_mm: 0.2,
            primary_secondary_clearance_mm: 12.6,
            min_trace_width_mm: 0.25,
            locality_mm: 3.0,
            primary_nets: vec!["PRIMARY_IN".into(), "PRIMARY_OUT".into()],
            secondary_nets: net_names
                .into_iter()
                .filter(|name| name != "PRIMARY_IN" && name != "PRIMARY_OUT")
                .collect(),
            required_routed_nets: Vec::new(),
            allowed_layers: vec!["F.Cu".into(), "B.Cu".into()],
        },
        applicability,
        // Authored placement guards use body-center distances; they are not
        // a replacement for decoupling impedance or timing qualification.
        locality: [
            ("c_comp_pos", "comp_pos", 5.0),
            ("c_comp_neg", "comp_neg", 5.0),
            ("c_or_bypass", "output_or", 8.0),
        ]
        .into_iter()
        .map(
            |(component, target, limit)| zapote_core::current_sense::LocalityRequirement {
                component: component.into(),
                target_component: target.into(),
                max_distance_mm: limit,
            },
        )
        .collect(),
        source_value_bindings,
    };
    let board_sha256 = native.board_sha256.clone();
    let extractor_sha256 = native.extractor_sha256.clone();
    Ok(CurrentSenseInput {
        schema: zapote_core::current_sense::INPUT_SCHEMA.into(),
        profile,
        native,
        identity: CurrentSenseIdentity {
            source_manifest_sha256: digest(source_manifest_utf8.as_bytes()),
            profile_sha256: digest(profile_utf8.as_bytes()),
            native_export_sha256: digest(native_export_utf8.as_bytes()),
            model_sha256: digest(model_utf8.as_bytes()),
            board_sha256,
            extractor_sha256,
            source_revision: source_value["source"].as_str().unwrap_or("UNKNOWN").into(),
        },
        source_manifest_utf8,
        profile_utf8,
        native_export_utf8,
        model_utf8,
        model,
        source_components,
        source_bindings,
    })
}
