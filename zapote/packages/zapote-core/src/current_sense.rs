//! Source-bound contract for the standalone transformer current-sensing unit.
//!
//! The circuit owner supplies the concrete profile.  This module deliberately
//! contains no component values or RTD assumptions; it only defines the
//! evidence boundary that the ERC/DRC validators consume.

use crate::unit::{SourceComponent, SourcePadNet, UnitNativeEvidence};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

pub const INPUT_SCHEMA: &str = "zapote.current-sense.input.v1";
pub const PROFILE_SCHEMA: &str = "zapote.current-sense.profile.v1";
const OWNER_PROFILE_SCHEMA: &str = "zapote.current_sense_profile.v1";

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CurrentSenseInput {
    pub schema: String,
    pub profile: CurrentSenseProfile,
    pub native: UnitNativeEvidence,
    pub identity: CurrentSenseIdentity,
    /// Exact UTF-8 bytes emitted from the source compiler.
    pub source_manifest_utf8: String,
    /// Exact UTF-8 bytes used to produce `profile`.
    pub profile_utf8: String,
    /// Exact UTF-8 bytes emitted by the native KiCad extractor.
    pub native_export_utf8: String,
    /// Exact UTF-8 bytes emitted by the independent electrical model.
    pub model_utf8: String,
    pub model: serde_json::Value,
    /// Complete source census.  A partial expected-net list is not sufficient.
    pub source_components: Vec<SourceComponent>,
    pub source_bindings: Vec<SourcePadNet>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CurrentSenseIdentity {
    pub source_manifest_sha256: String,
    pub profile_sha256: String,
    pub native_export_sha256: String,
    pub model_sha256: String,
    pub board_sha256: String,
    pub extractor_sha256: String,
    #[serde(default)]
    pub source_revision: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CurrentSenseProfile {
    pub schema: String,
    pub profile_id: String,
    pub source_module: String,
    pub component_roles: Vec<CurrentSenseComponentRole>,
    pub interface_pins: Vec<CurrentSenseInterfacePin>,
    pub nets: Vec<CurrentSenseNet>,
    pub electrical: CurrentSenseElectricalProfile,
    pub geometry: CurrentSenseGeometry,
    pub applicability: Vec<ApplicabilityStatement>,
    #[serde(default)]
    pub locality: Vec<LocalityRequirement>,
    /// Values that the electrical equations consume, bound to source compiler
    /// attributes so a producer cannot rehash an arbitrary numeric profile.
    #[serde(default)]
    pub source_value_bindings: Vec<SourceValueBinding>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CurrentSenseComponentRole {
    pub role: String,
    pub instance_id: String,
    pub mpn: String,
    #[serde(default)]
    pub kind: String,
    /// Optional source compiler value (for example `4.99ohm`).  If present,
    /// the manifest's source_attributes must carry the same value.
    #[serde(default)]
    pub value: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CurrentSenseInterfacePin {
    pub name: String,
    pub component: String,
    pub pin: String,
    pub net: String,
    pub direction: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CurrentSenseNet {
    pub name: String,
    pub domain: String,
    pub role: String,
    #[serde(default)]
    pub required_copper: bool,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct NumericRange {
    pub min: f64,
    pub max: f64,
}

impl NumericRange {
    pub fn is_valid(&self) -> bool {
        self.min.is_finite() && self.max.is_finite() && self.min <= self.max
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CurrentSenseElectricalProfile {
    pub formula_revision: String,
    pub rail_voltage_v: NumericRange,
    pub ct_ratio: NumericRange,
    pub input_current_peak_a: NumericRange,
    /// Product requirement: the primary overcurrent threshold window is fixed
    /// by the reviewed requirement, independent of producer profile edits.
    pub ocp_threshold_current_a: NumericRange,
    pub burden_resistance_ohm: NumericRange,
    pub bias_top_ohm: NumericRange,
    pub bias_bottom_ohm: NumericRange,
    pub threshold_high_top_ohm: NumericRange,
    pub threshold_high_bottom_ohm: NumericRange,
    pub threshold_low_top_ohm: NumericRange,
    pub threshold_low_bottom_ohm: NumericRange,
    #[serde(default)]
    pub clamp_leakage_a: NumericRange,
    #[serde(default)]
    pub sense_input_bias_a: NumericRange,
    #[serde(default)]
    pub threshold_input_bias_a: NumericRange,
    #[serde(default)]
    pub sense_series_resistance_ohm: NumericRange,
    #[serde(default)]
    pub host_monitor_load_a: NumericRange,
    #[serde(default)]
    pub comparator_positive_offset_v: NumericRange,
    #[serde(default)]
    pub comparator_negative_offset_v: NumericRange,
    pub sensed_current_reference_a: f64,
    pub source_frequency_hz: NumericRange,
    pub operating_current_peak_a: f64,
    pub operating_frequency_hz: f64,
    pub response_limit_us: f64,
    #[serde(default)]
    pub burden_power_limit_w: Option<f64>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CurrentSenseGeometry {
    pub copper_layers: u8,
    pub clearance_mm: f64,
    pub primary_secondary_clearance_mm: f64,
    pub min_trace_width_mm: f64,
    pub locality_mm: f64,
    pub primary_nets: Vec<String>,
    pub secondary_nets: Vec<String>,
    #[serde(default)]
    pub required_routed_nets: Vec<String>,
    #[serde(default)]
    pub allowed_layers: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ApplicabilityStatement {
    pub topic: String,
    pub status: String,
    #[serde(default)]
    pub evidence: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LocalityRequirement {
    pub component: String,
    pub target_component: String,
    pub max_distance_mm: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SourceValueBinding {
    pub instance_id: String,
    pub attribute: String,
    pub value: String,
    #[serde(default)]
    pub quantity: String,
}

impl CurrentSenseProfile {
    pub fn validate(&self) -> Vec<String> {
        let mut errors = Vec::new();
        if self.schema != PROFILE_SCHEMA {
            errors.push(format!(
                "current-sense profile schema must be {PROFILE_SCHEMA}"
            ));
        }
        if self.profile_id.trim().is_empty() || self.source_module.trim().is_empty() {
            errors.push("current-sense profile_id and source_module are required".into());
        }
        let mut roles = std::collections::BTreeSet::new();
        let mut instances = std::collections::BTreeSet::new();
        for role in &self.component_roles {
            if role.role.trim().is_empty()
                || role.instance_id.trim().is_empty()
                || role.mpn.trim().is_empty()
            {
                errors.push(
                    "current-sense component roles require role, instance_id, and mpn".into(),
                );
            }
            if !roles.insert(role.role.as_str()) {
                errors.push(format!(
                    "duplicate current-sense component role {}",
                    role.role
                ));
            }
            if !instances.insert(role.instance_id.as_str()) {
                errors.push(format!(
                    "duplicate current-sense component {}",
                    role.instance_id
                ));
            }
        }
        let mut names = std::collections::BTreeSet::new();
        for pin in &self.interface_pins {
            if pin.name.trim().is_empty()
                || pin.component.trim().is_empty()
                || pin.pin.trim().is_empty()
                || pin.net.trim().is_empty()
            {
                errors.push(
                    "current-sense interface pins require name, component, pin, and net".into(),
                );
            }
            if !names.insert(pin.name.as_str()) {
                errors.push(format!(
                    "duplicate current-sense interface pin {}",
                    pin.name
                ));
            }
        }
        let mut net_names = std::collections::BTreeSet::new();
        for net in &self.nets {
            if net.name.trim().is_empty() || net.domain.trim().is_empty() {
                errors.push("current-sense nets require name and domain".into());
            }
            if !net_names.insert(net.name.as_str()) {
                errors.push(format!("duplicate current-sense net {}", net.name));
            }
        }
        let e = &self.electrical;
        if e.formula_revision.trim().is_empty() {
            errors.push("current-sense electrical formula_revision is required".into());
        }
        for (name, range) in [
            ("rail_voltage_v", &e.rail_voltage_v),
            ("ct_ratio", &e.ct_ratio),
            ("input_current_peak_a", &e.input_current_peak_a),
            ("ocp_threshold_current_a", &e.ocp_threshold_current_a),
            ("burden_resistance_ohm", &e.burden_resistance_ohm),
            ("bias_top_ohm", &e.bias_top_ohm),
            ("bias_bottom_ohm", &e.bias_bottom_ohm),
            ("threshold_high_top_ohm", &e.threshold_high_top_ohm),
            ("threshold_high_bottom_ohm", &e.threshold_high_bottom_ohm),
            ("threshold_low_top_ohm", &e.threshold_low_top_ohm),
            ("threshold_low_bottom_ohm", &e.threshold_low_bottom_ohm),
            ("clamp_leakage_a", &e.clamp_leakage_a),
            ("sense_input_bias_a", &e.sense_input_bias_a),
            ("threshold_input_bias_a", &e.threshold_input_bias_a),
            (
                "sense_series_resistance_ohm",
                &e.sense_series_resistance_ohm,
            ),
            ("host_monitor_load_a", &e.host_monitor_load_a),
            (
                "comparator_positive_offset_v",
                &e.comparator_positive_offset_v,
            ),
            (
                "comparator_negative_offset_v",
                &e.comparator_negative_offset_v,
            ),
            ("source_frequency_hz", &e.source_frequency_hz),
        ] {
            if !range.is_valid() {
                errors.push(format!("current-sense electrical range {name} is invalid"));
            }
        }
        if e.ocp_threshold_current_a.min != 45.0 || e.ocp_threshold_current_a.max != 55.0 {
            errors
                .push("current-sense OCP threshold window must remain exactly 45..55 Apeak".into());
        }
        if e.response_limit_us <= 0.0 || !e.response_limit_us.is_finite() {
            errors.push("current-sense response_limit_us must be finite and positive".into());
        }
        for (name, value) in [
            ("sensed_current_reference_a", e.sensed_current_reference_a),
            ("operating_current_peak_a", e.operating_current_peak_a),
            ("operating_frequency_hz", e.operating_frequency_hz),
        ] {
            if !value.is_finite() || value <= 0.0 {
                errors.push(format!("current-sense {name} must be finite and positive"));
            }
        }
        if e.burden_power_limit_w
            .is_some_and(|v| v <= 0.0 || !v.is_finite())
        {
            errors.push("current-sense burden_power_limit_w must be finite and positive".into());
        }
        let g = &self.geometry;
        if g.copper_layers == 0
            || !g.clearance_mm.is_finite()
            || g.clearance_mm <= 0.0
            || !g.primary_secondary_clearance_mm.is_finite()
            || g.primary_secondary_clearance_mm <= 0.0
            || !g.min_trace_width_mm.is_finite()
            || g.min_trace_width_mm <= 0.0
            || !g.locality_mm.is_finite()
            || g.locality_mm <= 0.0
        {
            errors.push("current-sense geometry bounds must be finite and positive".into());
        }
        let primary: std::collections::BTreeSet<_> =
            g.primary_nets.iter().map(String::as_str).collect();
        let secondary: std::collections::BTreeSet<_> =
            g.secondary_nets.iter().map(String::as_str).collect();
        if primary.is_empty() || secondary.is_empty() {
            errors.push("current-sense primary_nets and secondary_nets are required".into());
        }
        if primary.intersection(&secondary).next().is_some() {
            errors.push("current-sense primary and secondary net sets must be disjoint".into());
        }
        for requirement in &self.locality {
            if requirement.component.trim().is_empty()
                || requirement.target_component.trim().is_empty()
                || requirement.max_distance_mm <= 0.0
                || !requirement.max_distance_mm.is_finite()
            {
                errors
                    .push("current-sense locality requirements must be finite and positive".into());
            }
        }
        if self.source_value_bindings.is_empty() {
            errors.push("current-sense electrical profile requires source_value_bindings".into());
        }
        for binding in &self.source_value_bindings {
            if binding.instance_id.trim().is_empty()
                || binding.attribute.trim().is_empty()
                || binding.value.trim().is_empty()
            {
                errors.push(
                    "current-sense source value bindings require instance, attribute, and value"
                        .into(),
                );
            }
            if !binding.quantity.is_empty()
                && !matches!(
                    binding.quantity.as_str(),
                    "burden_resistance_ohm"
                        | "sense_series_resistance_ohm"
                        | "rail_voltage_v"
                        | "ct_ratio"
                        | "bias_top_ohm"
                        | "bias_bottom_ohm"
                        | "threshold_high_top_ohm"
                        | "threshold_high_bottom_ohm"
                        | "threshold_low_top_ohm"
                        | "threshold_low_bottom_ohm"
                )
            {
                errors.push(format!(
                    "unsupported current-sense source value quantity {}",
                    binding.quantity
                ));
            }
        }
        if self.applicability.is_empty() {
            errors.push("current-sense applicability statements are required".into());
        }
        errors
    }
}

fn sha256_hex(bytes: &[u8]) -> String {
    Sha256::digest(bytes)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

fn parse_equal(raw: &str, expected: &serde_json::Value, name: &str, errors: &mut Vec<String>) {
    match serde_json::from_str::<serde_json::Value>(raw) {
        Ok(value) if &value == expected => {}
        Ok(_) => errors.push(format!("{name} parses but does not match typed input")),
        Err(error) => errors.push(format!("{name} is not valid JSON: {error}")),
    }
}

fn validate_native_pad_geometry(raw: &str, errors: &mut Vec<String>) {
    let Ok(native) = serde_json::from_str::<serde_json::Value>(raw) else {
        return;
    };
    let Some(components) = native
        .get("components")
        .and_then(serde_json::Value::as_array)
    else {
        return;
    };
    for component in components {
        let component_id = component
            .get("id")
            .and_then(serde_json::Value::as_str)
            .unwrap_or("<unknown>");
        let Some(pads) = component
            .get("footprint_pads")
            .and_then(serde_json::Value::as_array)
        else {
            continue;
        };
        for pad in pads {
            let pad_id = pad
                .get("pad")
                .and_then(serde_json::Value::as_str)
                .unwrap_or("<unknown>");
            let object = format!("native.{component_id}.{pad_id}");
            let Some(shape) = pad.get("shape").and_then(serde_json::Value::as_u64) else {
                errors.push(format!("{object} requires native numeric shape"));
                continue;
            };
            if !matches!(shape, 0..=2 | 4) {
                errors.push(format!("{object} has unsupported native pad shape {shape}"));
            }
            let Some(drill) = pad.get("drill_mm").and_then(serde_json::Value::as_array) else {
                errors.push(format!("{object} requires native drill_mm"));
                continue;
            };
            if drill.len() != 2
                || drill.iter().any(|value| {
                    value
                        .as_f64()
                        .is_none_or(|dimension| !dimension.is_finite() || dimension < 0.0)
                })
            {
                errors.push(format!("{object} has invalid native drill_mm"));
            }
            let Some(ratio) = pad.get("roundrect_ratio") else {
                errors.push(format!("{object} requires native roundrect_ratio"));
                continue;
            };
            if ratio
                .as_f64()
                .is_none_or(|value| !value.is_finite() || !(0.0..=0.5).contains(&value))
            {
                errors.push(format!("{object} has invalid native roundrect_ratio"));
            }
        }
    }
}

fn number_at(value: &serde_json::Value, path: &[&str]) -> Option<f64> {
    path.iter()
        .try_fold(value, |current, key| current.get(*key))
        .and_then(serde_json::Value::as_f64)
}

fn range_matches(value: f64, range: &NumericRange, tolerance: f64) -> bool {
    value.is_finite()
        && range.min <= value * (1.0 + tolerance)
        && range.max >= value * (1.0 - tolerance)
}

fn owner_profile_compatible(raw: &str, profile: &CurrentSenseProfile) -> bool {
    let Ok(value) = serde_json::from_str::<serde_json::Value>(raw) else {
        return false;
    };
    if !matches!(
        value["schema"].as_str(),
        Some(PROFILE_SCHEMA) | Some(OWNER_PROFILE_SCHEMA)
    ) || value["unit"].as_str() != Some(profile.profile_id.as_str())
    {
        return false;
    }
    let e = &profile.electrical;
    let Some(ratio) = number_at(&value, &["transformer", "ratio_primary_to_secondary"]) else {
        return false;
    };
    if !range_matches(ratio, &e.ct_ratio, 0.0) {
        return false;
    }
    let Some(burden) = number_at(&value, &["front_end", "burden_ohm"]) else {
        return false;
    };
    if !range_matches(burden, &e.burden_resistance_ohm, 0.01) {
        return false;
    }
    let resistor_fields = [
        (&["bias_top_ohm"][..], &e.bias_top_ohm),
        (&["bias_bottom_ohm"][..], &e.bias_bottom_ohm),
        (&["threshold_high_top_ohm"][..], &e.threshold_high_top_ohm),
        (
            &["threshold_high_bottom_ohm"][..],
            &e.threshold_high_bottom_ohm,
        ),
        (&["threshold_low_top_ohm"][..], &e.threshold_low_top_ohm),
        (
            &["threshold_low_bottom_ohm"][..],
            &e.threshold_low_bottom_ohm,
        ),
    ];
    let tolerance =
        number_at(&value, &["front_end", "threshold_tolerance_fraction"]).unwrap_or(0.001);
    for (name, range) in resistor_fields {
        let Some(actual) = number_at(&value, &["front_end", name[0]]) else {
            return false;
        };
        if !range_matches(
            actual,
            range,
            if name[0] == "bias_top_ohm" || name[0] == "bias_bottom_ohm" {
                number_at(&value, &["front_end", "bias_tolerance_fraction"]).unwrap_or(tolerance)
            } else {
                tolerance
            },
        ) {
            return false;
        }
    }
    value["requirements"]["ocp_peak_a"]
        .as_array()
        .is_some_and(|values| {
            values.len() == 2
                && values[0].as_f64() == Some(e.ocp_threshold_current_a.min)
                && values[1].as_f64() == Some(e.ocp_threshold_current_a.max)
        })
}

fn leading_number(value: &str) -> Option<f64> {
    let trimmed = value.trim().to_ascii_lowercase();
    let token = trimmed
        .trim()
        .split(|character: char| !(character.is_ascii_digit() || matches!(character, '.' | '-')))
        .find(|token| !token.is_empty())?;
    let mut number: f64 = token.parse().ok()?;
    let suffix = &trimmed[token.len()..];
    if suffix.starts_with("kohm") || suffix.starts_with("kω") {
        number *= 1_000.0;
    } else if suffix.starts_with("mohm") {
        number *= 1_000_000.0;
    } else if suffix.starts_with("nf") {
        number *= 1e-9;
    } else if suffix.starts_with("uf") {
        number *= 1e-6;
    }
    Some(number)
}

fn source_quantity_matches(
    quantity: &str,
    value: f64,
    electrical: &CurrentSenseElectricalProfile,
) -> bool {
    let range = match quantity {
        "burden_resistance_ohm" => &electrical.burden_resistance_ohm,
        "sense_series_resistance_ohm" => &electrical.sense_series_resistance_ohm,
        "rail_voltage_v" => &electrical.rail_voltage_v,
        "ct_ratio" => &electrical.ct_ratio,
        "bias_top_ohm" => &electrical.bias_top_ohm,
        "bias_bottom_ohm" => &electrical.bias_bottom_ohm,
        "threshold_high_top_ohm" => &electrical.threshold_high_top_ohm,
        "threshold_high_bottom_ohm" => &electrical.threshold_high_bottom_ohm,
        "threshold_low_top_ohm" => &electrical.threshold_low_top_ohm,
        "threshold_low_bottom_ohm" => &electrical.threshold_low_bottom_ohm,
        _ => return false,
    };
    range.min <= value && value <= range.max
}

/// Extract the complete typed census from the source compiler's production
/// manifest. Bridge net nodes are references; strict_pin_map entries use
/// instance paths, so this resolver is intentionally explicit.
pub fn source_census_from_manifest(
    raw: &str,
) -> Result<(Vec<SourceComponent>, Vec<SourcePadNet>), Vec<String>> {
    let manifest = serde_json::from_str::<serde_json::Value>(raw)
        .map_err(|error| vec![format!("source manifest is not JSON: {error}")])?;
    let bridge_components = manifest["bridge"]["components"]
        .as_array()
        .ok_or_else(|| vec!["source manifest bridge.components is required".into()])?;
    let source_components = manifest["components"]
        .as_array()
        .ok_or_else(|| vec!["source manifest components is required".into()])?;
    let pin_map = manifest["strict_pin_map"]
        .as_array()
        .ok_or_else(|| vec!["source manifest strict_pin_map is required".into()])?;
    let reference_to_instance: std::collections::BTreeMap<_, _> = bridge_components
        .iter()
        .filter_map(|component| {
            Some((
                component["reference"].as_str()?.to_owned(),
                component["instance_path"].as_str()?.to_owned(),
            ))
        })
        .collect();
    let mut components = Vec::new();
    for component in source_components {
        let Some(instance) = component["instance_path"].as_str() else {
            continue;
        };
        let Some(mpn) = component["mpn"].as_str() else {
            continue;
        };
        let pad_count = pin_map
            .iter()
            .filter(|entry| entry["instance_path"].as_str() == Some(instance))
            .count();
        components.push(SourceComponent {
            instance_id: instance.into(),
            mpn: mpn.into(),
            pad_count,
        });
    }
    let mut bindings = Vec::new();
    let mut errors = Vec::new();
    for entry in pin_map {
        let (Some(instance), Some(pad), Some(reference), Some(pin)) = (
            entry["instance_path"].as_str(),
            entry["pad"].as_str(),
            entry["reference"].as_str(),
            entry["pin"].as_str(),
        ) else {
            errors.push("source manifest strict_pin_map entry is incomplete".into());
            continue;
        };
        let net = manifest["bridge"]["nets"]
            .as_array()
            .into_iter()
            .flatten()
            .find_map(|net| {
                let nodes = net["nodes"].as_array()?;
                nodes
                    .iter()
                    .any(|node| {
                        let pair = node.as_array();
                        pair.is_some_and(|pair| {
                            pair.len() == 2
                                && pair[0].as_str().is_some_and(|node_id| {
                                    node_id == instance
                                        || reference_to_instance
                                            .get(node_id)
                                            .is_some_and(|mapped| mapped == instance)
                                })
                                && pair[1].as_str() == Some(pin)
                        })
                    })
                    .then(|| net["name"].as_str().map(str::to_owned))
                    .flatten()
            });
        match net {
            Some(net) => bindings.push(SourcePadNet {
                instance_id: instance.into(),
                pad: pad.into(),
                net,
            }),
            None => errors.push(format!(
                "source manifest strict_pin_map entry {instance}.{pin} lacks bridge net"
            )),
        }
        if reference_to_instance.get(reference).map(String::as_str) != Some(instance) {
            errors.push(format!(
                "source manifest strict_pin_map entry {instance}.{pin} lacks bridge reference"
            ));
        }
    }
    if errors.is_empty() {
        Ok((components, bindings))
    } else {
        Err(errors)
    }
}

impl CurrentSenseInput {
    pub fn validate(&self) -> Vec<String> {
        let mut errors = self.profile.validate();
        if self.schema != INPUT_SCHEMA {
            errors.push(format!("current-sense input schema must be {INPUT_SCHEMA}"));
        }
        let hashes = [
            (
                "source_manifest",
                &self.identity.source_manifest_sha256,
                self.source_manifest_utf8.as_bytes(),
            ),
            (
                "profile",
                &self.identity.profile_sha256,
                self.profile_utf8.as_bytes(),
            ),
            (
                "native_export",
                &self.identity.native_export_sha256,
                self.native_export_utf8.as_bytes(),
            ),
            (
                "model",
                &self.identity.model_sha256,
                self.model_utf8.as_bytes(),
            ),
        ];
        for (name, claimed, bytes) in hashes {
            if !crate::is_sha256(claimed) {
                errors.push(format!(
                    "current-sense identity {name} must be a SHA-256 digest"
                ));
            } else if sha256_hex(bytes) != *claimed {
                errors.push(format!(
                    "current-sense {name} bytes do not match its SHA-256 identity"
                ));
            }
        }
        for (name, value) in [
            ("board", &self.identity.board_sha256),
            ("extractor", &self.identity.extractor_sha256),
        ] {
            if !crate::is_sha256(value) {
                errors.push(format!(
                    "current-sense identity {name} must be a SHA-256 digest"
                ));
            }
        }
        if self.identity.board_sha256 != self.native.board_sha256 {
            errors.push("current-sense board identity does not match native board identity".into());
        }
        if self.identity.extractor_sha256 != self.native.extractor_sha256 {
            errors.push(
                "current-sense extractor identity does not match native extractor identity".into(),
            );
        }
        let profile_value = serde_json::to_value(&self.profile).unwrap_or_default();
        let native_value = serde_json::to_value(&self.native).unwrap_or_default();
        if serde_json::from_str::<serde_json::Value>(&self.profile_utf8)
            .ok()
            .as_ref()
            != Some(&profile_value)
            && !owner_profile_compatible(&self.profile_utf8, &self.profile)
        {
            errors.push(
                "profile_utf8 does not match typed profile or owner profile projection".into(),
            );
        }
        match serde_json::from_str::<UnitNativeEvidence>(&self.native_export_utf8) {
            Ok(parsed) if serde_json::to_value(&parsed).unwrap_or_default() == native_value => {}
            Ok(_) => errors
                .push("native_export_utf8 typed projection does not match native evidence".into()),
            Err(error) => errors.push(format!(
                "native_export_utf8 is not valid native evidence JSON: {error}"
            )),
        }
        validate_native_pad_geometry(&self.native_export_utf8, &mut errors);
        validate_source_manifest(self, &mut errors);
        parse_equal(&self.model_utf8, &self.model, "model_utf8", &mut errors);
        if self.source_components.is_empty() || self.source_bindings.is_empty() {
            errors.push("complete source component and pad binding censuses are required".into());
        }
        let mut source_ids = std::collections::BTreeSet::new();
        for source in &self.source_components {
            if !source_ids.insert(source.instance_id.as_str()) {
                errors.push(format!("duplicate source component {}", source.instance_id));
            }
            let native = self
                .native
                .components
                .iter()
                .find(|component| component.id == source.instance_id);
            if native.map(|component| component.mpn.as_str()) != Some(source.mpn.as_str()) {
                errors.push(format!(
                    "source component {} MPN disagrees with native evidence",
                    source.instance_id
                ));
            }
            if native.map(|component| component.footprint_pads.len()) != Some(source.pad_count) {
                errors.push(format!(
                    "source component {} pad count disagrees with native evidence",
                    source.instance_id
                ));
            }
        }
        if source_ids.len() != self.native.components.len()
            || self
                .native
                .components
                .iter()
                .any(|component| !source_ids.contains(component.id.as_str()))
        {
            errors.push("source/native component census is not exact".into());
        }
        let mut binding_keys = std::collections::BTreeSet::new();
        for binding in &self.source_bindings {
            if !binding_keys.insert((binding.instance_id.as_str(), binding.pad.as_str())) {
                errors.push(format!(
                    "duplicate source pad binding {}.{}",
                    binding.instance_id, binding.pad
                ));
            }
            let observed = self
                .native
                .components
                .iter()
                .find(|component| component.id == binding.instance_id)
                .and_then(|component| {
                    component
                        .footprint_pads
                        .iter()
                        .find(|pad| pad.pad == binding.pad)
                });
            if observed.map(|pad| pad.net.as_str()) != Some(binding.net.as_str()) {
                errors.push(format!(
                    "source binding {}.{} disagrees with native pad net",
                    binding.instance_id, binding.pad
                ));
            }
        }
        let native_keys: std::collections::BTreeSet<_> = self
            .native
            .components
            .iter()
            .flat_map(|component| {
                component
                    .footprint_pads
                    .iter()
                    .map(move |pad| (component.id.as_str(), pad.pad.as_str()))
            })
            .collect();
        if native_keys != binding_keys {
            errors.push("source pad binding census is not exact".into());
        }
        errors
    }
}

/// Validate the actual source compiler manifest shape.  The bridge and strict
/// pin map are authoritative: a simplified component/net projection would let
/// a producer omit a pin while still appearing to match its own census.
fn validate_source_manifest(input: &CurrentSenseInput, errors: &mut Vec<String>) {
    let Ok(manifest) = serde_json::from_str::<serde_json::Value>(&input.source_manifest_utf8)
    else {
        errors.push("source_manifest_utf8 is not valid JSON".into());
        return;
    };
    let Some(bridge) = manifest
        .get("bridge")
        .and_then(serde_json::Value::as_object)
    else {
        errors.push("source manifest bridge is required".into());
        return;
    };
    let Some(bridge_components) = bridge
        .get("components")
        .and_then(serde_json::Value::as_array)
    else {
        errors.push("source manifest bridge.components is required".into());
        return;
    };
    let Some(bridge_nets) = bridge.get("nets").and_then(serde_json::Value::as_array) else {
        errors.push("source manifest bridge.nets is required".into());
        return;
    };
    let Some(pin_map) = manifest
        .get("strict_pin_map")
        .and_then(serde_json::Value::as_array)
    else {
        errors.push("source manifest strict_pin_map is required".into());
        return;
    };
    let Some(attributes) = manifest
        .get("source_attributes")
        .and_then(serde_json::Value::as_object)
    else {
        errors.push("source manifest source_attributes is required".into());
        return;
    };
    let mut manifest_components = std::collections::BTreeSet::new();
    let reference_to_instance: std::collections::BTreeMap<_, _> = bridge_components
        .iter()
        .filter_map(|component| {
            Some((
                component.get("reference")?.as_str()?.to_owned(),
                component.get("instance_path")?.as_str()?.to_owned(),
            ))
        })
        .collect();
    for component in bridge_components {
        let Some(instance) = component
            .get("instance_path")
            .and_then(serde_json::Value::as_str)
        else {
            errors.push("source manifest bridge component lacks instance_path".into());
            continue;
        };
        let Some(reference) = component
            .get("reference")
            .and_then(serde_json::Value::as_str)
        else {
            errors.push(format!(
                "source manifest component {instance} lacks reference"
            ));
            continue;
        };
        manifest_components.insert(instance.to_owned());
        if !input
            .source_components
            .iter()
            .any(|source| source.instance_id == instance)
        {
            errors.push(format!(
                "source manifest component {instance} is absent from typed census"
            ));
        }
        if !attributes.contains_key(instance) {
            errors.push(format!(
                "source manifest component {instance} lacks source_attributes"
            ));
        } else if let Some(source) = input
            .source_components
            .iter()
            .find(|source| source.instance_id == instance)
        {
            let attribute = attributes
                .get(instance)
                .and_then(serde_json::Value::as_object);
            if attribute
                .and_then(|value| value.get("mpn"))
                .and_then(serde_json::Value::as_str)
                != Some(source.mpn.as_str())
            {
                errors.push(format!(
                    "source manifest MPN for {instance} disagrees with typed census"
                ));
            }
            if let Some(role) = input
                .profile
                .component_roles
                .iter()
                .find(|role| role.instance_id == instance)
            {
                if let Some(expected_value) = role.value.as_deref() {
                    if attribute
                        .and_then(|value| value.get("value"))
                        .and_then(serde_json::Value::as_str)
                        != Some(expected_value)
                    {
                        errors.push(format!(
                            "source manifest value for {instance} disagrees with profile role"
                        ));
                    }
                }
            }
        }
        if !pin_map.iter().any(|entry| {
            entry
                .get("instance_path")
                .and_then(serde_json::Value::as_str)
                == Some(instance)
                && entry.get("reference").and_then(serde_json::Value::as_str) == Some(reference)
        }) {
            errors.push(format!(
                "source manifest strict_pin_map lacks {instance} reference {reference}"
            ));
        }
    }
    if manifest_components.len() != input.source_components.len()
        || input
            .source_components
            .iter()
            .any(|source| !manifest_components.contains(&source.instance_id))
    {
        errors.push("source manifest bridge component census is not exact".into());
    }

    for binding in &input.profile.source_value_bindings {
        let actual = attributes
            .get(&binding.instance_id)
            .and_then(serde_json::Value::as_object)
            .and_then(|attributes| attributes.get(&binding.attribute))
            .and_then(serde_json::Value::as_str);
        if actual != Some(binding.value.as_str()) {
            errors.push(format!(
                "source value {}.{} is {:?}, expected {:?}",
                binding.instance_id, binding.attribute, actual, binding.value
            ));
        }
        if !binding.quantity.is_empty() {
            match leading_number(&binding.value) {
                Some(value)
                    if source_quantity_matches(
                        &binding.quantity,
                        value,
                        &input.profile.electrical,
                    ) => {}
                Some(value) => errors.push(format!(
                    "source value {}={} is outside compiled electrical {} range",
                    binding.instance_id, value, binding.quantity
                )),
                None => errors.push(format!(
                    "source value {} is not numeric for {}",
                    binding.value, binding.quantity
                )),
            }
        }
    }

    let mut manifest_bindings = std::collections::BTreeSet::new();
    for entry in pin_map {
        let (Some(instance), Some(pad), Some(reference), Some(pin)) = (
            entry
                .get("instance_path")
                .and_then(serde_json::Value::as_str),
            entry.get("pad").and_then(serde_json::Value::as_str),
            entry.get("reference").and_then(serde_json::Value::as_str),
            entry.get("pin").and_then(serde_json::Value::as_str),
        ) else {
            errors.push("source manifest strict_pin_map entry is incomplete".into());
            continue;
        };
        if !bridge_components.iter().any(|component| {
            component
                .get("instance_path")
                .and_then(serde_json::Value::as_str)
                == Some(instance)
                && component
                    .get("reference")
                    .and_then(serde_json::Value::as_str)
                    == Some(reference)
        }) {
            errors.push(format!(
                "source manifest strict_pin_map entry {instance}.{pin} lacks bridge component"
            ));
        }
        let net = bridge_nets.iter().find_map(|net| {
            let nodes = net.get("nodes")?.as_array()?;
            nodes
                .iter()
                .any(|node| {
                    node.as_array().is_some_and(|pair| {
                        pair.len() == 2
                            && pair[0].as_str().is_some_and(|node_id| {
                                node_id == instance
                                    || reference_to_instance
                                        .get(node_id)
                                        .is_some_and(|mapped| mapped == instance)
                            })
                            && pair[1].as_str() == Some(pin)
                    })
                })
                .then(|| net.get("name")?.as_str().map(str::to_owned))
                .flatten()
        });
        if let Some(net) = net {
            manifest_bindings.insert((instance.to_owned(), pad.to_owned(), net));
        } else {
            errors.push(format!(
                "source manifest strict_pin_map entry {instance}.{pin} lacks bridge net"
            ));
        }
    }
    for source in &input.source_components {
        let count = pin_map
            .iter()
            .filter(|entry| {
                entry
                    .get("instance_path")
                    .and_then(serde_json::Value::as_str)
                    == Some(source.instance_id.as_str())
            })
            .count();
        if count != source.pad_count {
            errors.push(format!(
                "source manifest strict_pin_map count for {} is {}, expected {}",
                source.instance_id, count, source.pad_count
            ));
        }
    }
    let typed_bindings: std::collections::BTreeSet<_> = input
        .source_bindings
        .iter()
        .map(|binding| {
            (
                binding.instance_id.clone(),
                binding.pad.clone(),
                binding.net.clone(),
            )
        })
        .collect();
    if manifest_bindings != typed_bindings {
        errors.push(
            "source manifest bridge/strict_pin_map bindings do not match typed source bindings"
                .into(),
        );
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn captured_source_manifest_uses_bridge_and_strict_pin_map_shape() {
        let manifest: serde_json::Value = serde_json::from_str(include_str!(
            "../../../fixtures/rtd-source-02-manifest.json"
        ))
        .expect("captured source manifest parses");
        let (resolved_components, resolved_bindings) = source_census_from_manifest(include_str!(
            "../../../fixtures/rtd-source-02-manifest.json"
        ))
        .expect("captured source census resolves");
        assert_eq!(resolved_components.len(), 52);
        assert_eq!(resolved_bindings.len(), 184);
        let mut source_components = Vec::new();
        for component in manifest["components"].as_array().expect("components") {
            let instance_id = component["instance_path"].as_str().expect("instance path");
            let mpn = component["mpn"].as_str().expect("mpn");
            let pad_count = manifest["strict_pin_map"]
                .as_array()
                .expect("strict pin map")
                .iter()
                .filter(|entry| entry["instance_path"].as_str() == Some(instance_id))
                .count();
            source_components.push(SourceComponent {
                instance_id: instance_id.into(),
                mpn: mpn.into(),
                pad_count,
            });
        }
        let mut source_bindings = Vec::new();
        let reference_to_instance: std::collections::BTreeMap<_, _> = manifest["bridge"]
            ["components"]
            .as_array()
            .expect("bridge components")
            .iter()
            .filter_map(|component| {
                Some((
                    component["reference"].as_str()?.to_owned(),
                    component["instance_path"].as_str()?.to_owned(),
                ))
            })
            .collect();
        for entry in manifest["strict_pin_map"]
            .as_array()
            .expect("strict pin map")
        {
            let instance = entry["instance_path"].as_str().expect("instance");
            let pin = entry["pin"].as_str().expect("pin");
            let net = manifest["bridge"]["nets"]
                .as_array()
                .expect("bridge nets")
                .iter()
                .find_map(|net| {
                    net["nodes"]
                        .as_array()?
                        .iter()
                        .any(|node| {
                            node.as_array().is_some_and(|pair| {
                                pair.len() == 2
                                    && pair[0].as_str().is_some_and(|node_id| {
                                        node_id == instance
                                            || reference_to_instance
                                                .get(node_id)
                                                .is_some_and(|mapped| mapped == instance)
                                    })
                                    && pair[1].as_str() == Some(pin)
                            })
                        })
                        .then(|| net["name"].as_str().map(str::to_owned))
                        .flatten()
                })
                .expect("bridge net");
            source_bindings.push(SourcePadNet {
                instance_id: instance.into(),
                pad: entry["pad"].as_str().expect("pad").into(),
                net,
            });
        }
        let profile = CurrentSenseProfile {
            schema: PROFILE_SCHEMA.into(),
            profile_id: "CurrentSenseUnit".into(),
            source_module: "captured".into(),
            component_roles: Vec::new(),
            interface_pins: Vec::new(),
            nets: Vec::new(),
            electrical: serde_json::from_value(serde_json::json!({
                "formula_revision":"captured","rail_voltage_v":{"min":3.3,"max":3.3},"ct_ratio":{"min":100.0,"max":100.0},"input_current_peak_a":{"min":0.0,"max":1.0},"ocp_threshold_current_a":{"min":45.0,"max":55.0},"burden_resistance_ohm":{"min":1.0,"max":1.0},"bias_top_ohm":{"min":47000.0,"max":47000.0},"bias_bottom_ohm":{"min":47000.0,"max":47000.0},"threshold_high_top_ohm":{"min":3740.0,"max":3740.0},"threshold_high_bottom_ohm":{"min":10000.0,"max":10000.0},"threshold_low_top_ohm":{"min":10000.0,"max":10000.0},"threshold_low_bottom_ohm":{"min":3740.0,"max":3740.0},"sensed_current_reference_a":88.0,"source_frequency_hz":{"min":20000.0,"max":100000.0},"operating_current_peak_a":28.76,"operating_frequency_hz":47000.0,"response_limit_us":1.0
            })).expect("electrical"),
            geometry: serde_json::from_value(serde_json::json!({"copper_layers":2,"clearance_mm":0.2,"primary_secondary_clearance_mm":1.0,"min_trace_width_mm":0.2,"locality_mm":3.0,"primary_nets":["P"],"secondary_nets":["S"]})).expect("geometry"),
            applicability: vec![ApplicabilityStatement { topic: "captured".into(), status: "qualified".into(), evidence: "fixture".into() }],
            locality: Vec::new(),
            source_value_bindings: Vec::new(),
        };
        let native = UnitNativeEvidence {
            polygon_max_error_mm: 0.0,
            board_sha256: "a".repeat(64),
            extractor_sha256: "b".repeat(64),
            copper_layer_count: 2,
            components: Vec::new(),
            connections: Vec::new(),
            connectivity_clusters: Vec::new(),
            traces: Vec::new(),
            vias: Vec::new(),
            zones: Vec::new(),
        };
        let input = CurrentSenseInput {
            schema: INPUT_SCHEMA.into(),
            profile,
            native,
            identity: CurrentSenseIdentity {
                source_manifest_sha256: "a".repeat(64),
                profile_sha256: "a".repeat(64),
                native_export_sha256: "a".repeat(64),
                model_sha256: "a".repeat(64),
                board_sha256: "a".repeat(64),
                extractor_sha256: "b".repeat(64),
                source_revision: "captured".into(),
            },
            source_manifest_utf8: serde_json::to_string(&manifest).expect("manifest bytes"),
            profile_utf8: "{}".into(),
            native_export_utf8: "{}".into(),
            model_utf8: "{}".into(),
            model: serde_json::Value::Null,
            source_components,
            source_bindings,
        };
        let mut errors = Vec::new();
        validate_source_manifest(&input, &mut errors);
        assert!(errors.is_empty(), "captured manifest rejected: {errors:?}");
    }
}
