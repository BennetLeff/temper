//! Standalone RTDUnit source/manufacturing contract.
//!
//! This profile is deliberately independent of the historical full-cooker
//! `RtdContract`. It describes the unit boundary and known loads while
//! retaining explicit deferred contracts for connector qualification and
//! future aggressors/reference consumers.

use crate::{
    Component, Connection, ConnectivityCluster, GeometryConstraints, NativeZone, Trace, Via,
};
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct UnitProfile {
    pub schema: String,
    pub profile_id: String,
    pub source_module: String,
    pub components: UnitComponents,
    pub interface: UnitInterface,
    pub probe: UnitProbeContract,
    pub local: UnitLocalContract,
    pub board: UnitBoardContract,
    pub loads: Vec<UnitLoad>,
    pub future_contracts: FutureContracts,
    #[serde(default)]
    pub component_bindings: Vec<UnitComponentBinding>,
    pub firmware: UnitFirmwareContract,
    /// Maximum measured unit fault indication latency after the fault is
    /// applied; the host handoff allowance is already deducted.
    pub fault_latency_limit_ms: f64,
    #[serde(default)]
    pub decoupling_bindings: Vec<UnitDecouplingBinding>,
    #[serde(default = "default_unit_geometry")]
    pub geometry: GeometryConstraints,
    #[serde(default)]
    pub return_planes: Vec<UnitReturnPlane>,
    #[serde(default)]
    pub fault_case_bindings: Vec<UnitFaultCaseBinding>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct UnitProbeContract {
    pub component: String,
    pub mpn: String,
    pub pins: Vec<UnitProbePin>,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct UnitProbePin {
    pub number: u8,
    pub role: String,
    pub net: String,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct UnitLocalContract {
    pub reference_component: String,
    pub reference_mpn: String,
    pub ferrite_component: String,
    pub ferrite_mpn: String,
    pub filtered_rail: String,
}

fn default_unit_geometry() -> GeometryConstraints {
    GeometryConstraints {
        polygon_max_error_mm: 0.0,
        sensitive_nets: Vec::new(),
        aggressors: Vec::new(),
        prohibited_connections: Vec::new(),
        required_locality_mm: 3.0,
        return_planes: Vec::new(),
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct UnitComponentBinding {
    pub role: String,
    pub instance_id: String,
    pub mpn: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct UnitDecouplingBinding {
    pub role: String,
    pub instance_id: String,
    pub mpn: String,
    pub capacitance_nf: f64,
    pub target_component: String,
    pub pad_nets: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct UnitReturnPlane {
    pub purpose: String,
    pub net: String,
    pub layer: String,
}

/// Authored mapping from the observed model's stable case name to the
/// physical fault semantics consumed by the shared checker.  The observation
/// file supplies outcomes; this profile supplies applicability only.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct UnitFaultCaseBinding {
    pub name: String,
    #[serde(default)]
    pub conductor_open: Option<String>,
    #[serde(default)]
    pub rail_loss: Option<String>,
    #[serde(default)]
    pub resistance_ohm: Option<f64>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct UnitFirmwareContract {
    pub cs_gpio: u16,
    pub drdy_gpio: u16,
    pub low_threshold_word: u16,
    pub high_threshold_word: u16,
    pub short_fault_ohm: f64,
    pub open_fault_ohm: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct UnitComponents {
    pub adc_mpn: String,
    pub supervisor_mpn: String,
    pub rref_mpn: String,
    pub rref_ohm: f64,
    pub rref_tolerance_pct: f64,
    pub rref_tcr_ppm_c: f64,
    pub divider_top_ohm: f64,
    pub divider_bottom_ohm: f64,
    pub decoupling_nf: f64,
    pub pullup_ohm: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct UnitInterface {
    pub connector_mpn: Option<String>,
    pub pins: Vec<UnitPin>,
    pub qualification_status: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct UnitPin {
    pub number: u8,
    pub net: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct UnitBoardContract {
    pub copper_layers: u8,
    pub min_finished_copper_um: f64,
    pub clearance_mm: f64,
    pub signal_width_mm: f64,
    pub power_return_width_mm: f64,
    pub via_diameter_mm: f64,
    pub via_drill_mm: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct UnitLoad {
    pub name: String,
    pub current_a: Option<f64>,
    pub status: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FutureContracts {
    pub reference_consumers: String,
    pub aggressors: String,
    pub model: String,
}

/// Thin native transport for a standalone unit. It intentionally carries no
/// inferred net domains or policy; those belong to the source profile.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct UnitNativeEvidence {
    #[serde(default)]
    pub polygon_max_error_mm: f64,
    pub board_sha256: String,
    pub extractor_sha256: String,
    /// Native extractor's measured copper layer count.  This name is kept
    /// equal to the exporter; it is not a policy alias invented by the
    /// binder.
    pub copper_layer_count: u8,
    pub components: Vec<Component>,
    pub connections: Vec<Connection>,
    pub connectivity_clusters: Vec<ConnectivityCluster>,
    pub traces: Vec<Trace>,
    pub vias: Vec<Via>,
    #[serde(default)]
    pub zones: Vec<NativeZone>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct UnitInput {
    pub schema: String,
    pub profile: UnitProfile,
    pub native: UnitNativeEvidence,
    pub identity: UnitIdentity,
    pub firmware: UnitFirmwareEvidence,
    pub model: serde_json::Value,
    /// Independent full-network qualification receipt.  This is intentionally
    /// outside `model`: the receipt binds the raw model bytes to the identity
    /// and must not create a self-referential hash.
    #[serde(default)]
    pub model_qualification: Option<serde_json::Value>,
    #[serde(default)]
    pub source_bindings: Vec<SourcePadNet>,
    /// Complete compiled component census used to prove that the binding is
    /// not merely a partial expected-net sample.
    #[serde(default)]
    pub source_components: Vec<SourceComponent>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SourcePadNet {
    pub instance_id: String,
    pub pad: String,
    pub net: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SourceComponent {
    pub instance_id: String,
    pub mpn: String,
    pub pad_count: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct UnitIdentity {
    pub profile_sha256: String,
    pub native_export_sha256: String,
    pub source_manifest_sha256: String,
    pub extractor_sha256: String,
    pub model_sha256: String,
    pub firmware_sha256: String,
    pub firmware_pins_sha256: String,
    pub board_sha256: String,
    #[serde(default)]
    pub binary_sha256: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct UnitFirmwareEvidence {
    pub cs_gpio: u16,
    pub drdy_gpio: u16,
    pub low_threshold_word: u16,
    pub high_threshold_word: u16,
    pub short_fault_ohm: f64,
    pub open_fault_ohm: f64,
}

impl UnitInput {
    pub fn validate(&self) -> Vec<String> {
        let mut errors = self.profile.validate();
        if self.schema != "zapote.rtd.unit-input.v1" {
            errors.push("unit input schema must be zapote.rtd.unit-input.v1".into());
        }
        for (name, hash) in [
            ("profile", &self.identity.profile_sha256),
            ("native export", &self.identity.native_export_sha256),
            ("source manifest", &self.identity.source_manifest_sha256),
            ("extractor", &self.identity.extractor_sha256),
            ("model", &self.identity.model_sha256),
            ("firmware", &self.identity.firmware_sha256),
            ("firmware pins", &self.identity.firmware_pins_sha256),
            ("board", &self.identity.board_sha256),
        ] {
            if !crate::is_sha256(hash) {
                errors.push(format!("unit identity {name} must be a SHA-256 digest"));
            }
        }
        if let Some(hash) = &self.identity.binary_sha256 {
            if !crate::is_sha256(hash) {
                errors.push("unit identity binary must be a SHA-256 digest".into());
            }
        }
        if self.identity.board_sha256 != self.native.board_sha256 {
            errors.push("unit identity board hash does not match native extraction hash".into());
        }
        if self.identity.extractor_sha256 != self.native.extractor_sha256 {
            errors
                .push("unit identity extractor hash does not match native extraction hash".into());
        }
        if self.firmware.cs_gpio != self.profile.firmware.cs_gpio
            || self.firmware.drdy_gpio != self.profile.firmware.drdy_gpio
            || self.firmware.low_threshold_word != self.profile.firmware.low_threshold_word
            || self.firmware.high_threshold_word != self.profile.firmware.high_threshold_word
            || self.firmware.short_fault_ohm != self.profile.firmware.short_fault_ohm
            || self.firmware.open_fault_ohm != self.profile.firmware.open_fault_ohm
        {
            errors.push("firmware source values do not match the unit profile".into());
        }
        let observed_faults = self
            .model
            .get("observed_faults")
            .or_else(|| self.model.get("fault_observations"))
            .or_else(|| self.model.get("fault_coverage"));
        match observed_faults.and_then(|value| value.as_array()) {
            Some(faults) if !faults.is_empty() => {
                if faults.iter().any(|fault| {
                    fault.get("name").and_then(|v| v.as_str()).is_none()
                        || fault
                            .get("observed_class")
                            .and_then(|v| v.as_str())
                            .is_none()
                        || fault.get("observed_detected").is_none()
                }) {
                    errors.push(
                        "unit model observations require name, observed_class, observed_detected, and observed_latency_ms".into(),
                    );
                }
            }
            _ => errors.push(
                "unit model must provide non-empty observed_faults/fault_observations; expected-only faults are insufficient".into(),
            ),
        }
        if !crate::is_sha256(&self.native.board_sha256)
            || !crate::is_sha256(&self.native.extractor_sha256)
        {
            errors.push("native unit evidence requires board and extractor SHA-256 hashes".into());
        }
        if self.native.copper_layer_count != self.profile.board.copper_layers {
            errors.push("native board layer count does not match standalone contract".into());
        }
        if self.native.components.is_empty() {
            errors.push("native unit evidence requires components".into());
        }
        let mut component_ids = std::collections::BTreeSet::new();
        for component in &self.native.components {
            if !component_ids.insert(component.id.as_str()) {
                errors.push(format!("duplicate native component {}", component.id));
            }
            if component.id.trim().is_empty() || component.mpn.trim().is_empty() {
                errors.push("native component IDs and MPNs are required".into());
            }
            if component.footprint_pads.is_empty() {
                errors.push(format!(
                    "native component {} has no pad geometry",
                    component.id
                ));
            }
        }
        for binding in &self.profile.component_bindings {
            match self
                .native
                .components
                .iter()
                .find(|c| c.id == binding.instance_id)
            {
                Some(component) if component.mpn == binding.mpn => {}
                Some(component) => errors.push(format!(
                    "unit {} {} has MPN {}; expected {}",
                    binding.role, binding.instance_id, component.mpn, binding.mpn
                )),
                None => errors.push(format!(
                    "unit {} source component {} is absent from native board",
                    binding.role, binding.instance_id
                )),
            }
        }
        for (role, expected_mpn) in [
            ("ADC", self.profile.components.adc_mpn.as_str()),
            (
                "supervisor",
                self.profile.components.supervisor_mpn.as_str(),
            ),
            ("RREF", self.profile.components.rref_mpn.as_str()),
        ] {
            if !self
                .native
                .components
                .iter()
                .any(|component| component.mpn == expected_mpn)
            {
                errors.push(format!(
                    "native unit is missing exact {role} MPN {expected_mpn}"
                ));
            }
        }
        let mut connection_pins = std::collections::BTreeSet::new();
        for binding in &self.profile.decoupling_bindings {
            match self
                .native
                .components
                .iter()
                .find(|c| c.id == binding.instance_id)
            {
                Some(component) if component.mpn == binding.mpn => {}
                Some(component) => errors.push(format!(
                    "unit {} {} has MPN {}; expected {}",
                    binding.role, binding.instance_id, component.mpn, binding.mpn
                )),
                None => errors.push(format!(
                    "unit {} source component {} is absent from native board",
                    binding.role, binding.instance_id
                )),
            }
        }
        let mut net_names = std::collections::BTreeSet::new();
        for component in &self.native.components {
            for pad in &component.footprint_pads {
                if pad.net.trim().is_empty() {
                    errors.push(format!(
                        "native pad {}.{} requires a net",
                        component.id, pad.pad
                    ));
                } else {
                    net_names.insert(pad.net.as_str());
                }
                if pad.position_mm.iter().any(|v| !v.is_finite())
                    || pad.size_mm.iter().any(|v| !v.is_finite() || *v <= 0.0)
                    || pad.layers.is_empty()
                {
                    errors.push(format!(
                        "native pad {}.{} has incomplete geometry",
                        component.id, pad.pad
                    ));
                }
            }
        }
        for connection in &self.native.connections {
            if !connection_pins.insert((connection.component.as_str(), connection.pin.as_str())) {
                errors.push(format!(
                    "duplicate native connection {}.{}",
                    connection.component, connection.pin
                ));
            }
            if !component_ids.contains(connection.component.as_str()) {
                errors.push(format!(
                    "native connection names absent component {}",
                    connection.component
                ));
            }
            if !net_names.contains(connection.net.as_str()) {
                errors.push(format!(
                    "native connection names absent net {}",
                    connection.net
                ));
            }
            let Some(component) = self
                .native
                .components
                .iter()
                .find(|c| c.id == connection.component)
            else {
                continue;
            };
            let Some(pad) = component
                .footprint_pads
                .iter()
                .find(|p| p.pad == connection.pin)
            else {
                errors.push(format!(
                    "native connection {}.{} has no pad geometry",
                    connection.component, connection.pin
                ));
                continue;
            };
            if pad.net != connection.net {
                errors.push(format!(
                    "native connection {}.{} net {} disagrees with pad net {}",
                    connection.component, connection.pin, connection.net, pad.net
                ));
            }
            let node = format!("{}.{}", connection.component, connection.pin);
            if !self.native.connectivity_clusters.iter().any(|cluster| {
                cluster.net == connection.net && cluster.nodes.iter().any(|n| n == &node)
            }) {
                errors.push(format!(
                    "native copper cluster omits endpoint {node} on {}",
                    connection.net
                ));
            }
        }
        if self.source_components.is_empty() {
            errors.push("compiled source component census is required".into());
        }
        if self.source_bindings.is_empty() {
            errors.push("complete compiled source pad/net bindings are required".into());
        } else {
            let mut source_keys = std::collections::BTreeSet::new();
            for expected in &self.source_bindings {
                if expected.instance_id.trim().is_empty()
                    || expected.pad.trim().is_empty()
                    || expected.net.trim().is_empty()
                {
                    errors.push("compiled source bindings require instance, pad, and net".into());
                }
                if !source_keys.insert((expected.instance_id.as_str(), expected.pad.as_str())) {
                    errors.push(format!(
                        "duplicate compiled source binding {}.{}",
                        expected.instance_id, expected.pad
                    ));
                }
                let observed = self
                    .native
                    .components
                    .iter()
                    .find(|c| c.id == expected.instance_id)
                    .and_then(|c| c.footprint_pads.iter().find(|p| p.pad == expected.pad))
                    .map(|p| p.net.as_str());
                if observed != Some(expected.net.as_str()) {
                    errors.push(format!(
                        "source binding {}.{} expects {}, observed {:?}",
                        expected.instance_id, expected.pad, expected.net, observed
                    ));
                }
            }
            let source_ids: std::collections::BTreeSet<_> = self
                .source_components
                .iter()
                .map(|component| component.instance_id.as_str())
                .collect();
            let expected_pad_count: usize = self
                .source_components
                .iter()
                .map(|component| component.pad_count)
                .sum();
            if source_ids.len() != self.source_components.len()
                || self.source_components.iter().any(|component| {
                    component.instance_id.trim().is_empty()
                        || component.mpn.trim().is_empty()
                        || component.pad_count == 0
                })
            {
                errors.push(
                    "compiled source component census has invalid or duplicate entries".into(),
                );
            }
            if self.source_bindings.len() != expected_pad_count {
                errors.push(format!(
                    "compiled source binding is partial: {} bindings for {} source pads",
                    self.source_bindings.len(),
                    expected_pad_count
                ));
            }
            if source_ids.len() != self.native.components.len()
                || self.native.components.iter().any(|component| {
                    !source_ids.contains(component.id.as_str())
                        || self.source_components.iter().all(|expected| {
                            expected.instance_id != component.id || expected.mpn != component.mpn
                        })
                })
            {
                errors.push(
                    "native component census does not exactly match compiled source components"
                        .into(),
                );
            }
            let observed_source_keys: std::collections::BTreeSet<_> = self
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
            if observed_source_keys.len() != expected_pad_count
                || observed_source_keys
                    != source_keys
                        .iter()
                        .copied()
                        .collect::<std::collections::BTreeSet<_>>()
            {
                errors.push(
                    "native pad census does not exactly match compiled source bindings".into(),
                );
            }
        }
        if self.native.connectivity_clusters.is_empty() {
            errors.push("native unit evidence requires copper connectivity clusters".into());
        }
        let mut zone_ids = std::collections::BTreeSet::new();
        for zone in &self.native.zones {
            if zone.id.trim().is_empty() || !zone_ids.insert(zone.id.as_str()) {
                errors.push(format!("duplicate or empty native zone {}", zone.id));
            }
            if zone.filled_polygons.is_empty() {
                errors.push(format!("native zone {} has no filled polygon", zone.id));
            }
        }
        for trace in &self.native.traces {
            if trace.id.trim().is_empty() || trace.net.trim().is_empty() {
                errors.push("native traces require stable UUID and net".into());
            }
            if !trace.width_mm.is_finite()
                || trace.width_mm <= 0.0
                || trace.points_mm.len() < 2
                || trace.points_mm.iter().flatten().any(|v| !v.is_finite())
            {
                errors.push(format!("native trace {} has invalid geometry", trace.id));
            }
        }
        for via in &self.native.vias {
            if via.id.trim().is_empty()
                || via.net.trim().is_empty()
                || via.position_mm.iter().any(|v| !v.is_finite())
                || !via.drill_mm.is_finite()
                || via.drill_mm <= 0.0
            {
                errors.push(format!("native via {} has invalid geometry", via.id));
            }
        }
        errors
    }
}

impl UnitProfile {
    pub fn validate(&self) -> Vec<String> {
        let mut errors = Vec::new();
        if self.schema != "zapote.rtd.unit.v1" {
            errors.push("unit schema must be zapote.rtd.unit.v1".into());
        }
        if self.profile_id != "RTDUnit" || self.source_module != "RTDUnit" {
            errors.push("unit profile must bind the compiled RTDUnit source".into());
        }
        if self.components.adc_mpn != "MAX31865AAP+" {
            errors.push("unit ADC MPN must be MAX31865AAP+".into());
        }
        if self.components.supervisor_mpn != "TPS389001DSER" {
            errors.push("unit supervisor MPN must be TPS389001DSER".into());
        }
        if self.components.rref_mpn != "RG2012V-431-W-T1"
            || self.components.rref_ohm != 430.0
            || self.components.rref_tolerance_pct != 0.05
            || self.components.rref_tcr_ppm_c != 5.0
        {
            errors.push("unit RREF must be RG2012V-431-W-T1, 430 ohm, 0.05%, 5 ppm/C".into());
        }
        if self.components.divider_top_ohm != 16_500.0
            || self.components.divider_bottom_ohm != 10_000.0
            || self.components.decoupling_nf != 1.0
            || self.components.pullup_ohm != 1_000_000.0
        {
            errors.push("unit divider/decoupling values do not match the source proposal".into());
        }
        let expected_nets = [
            "+3V3",
            "GND",
            "GND",
            "RTD_SCK",
            "RTD_SDI",
            "RTD_SDO",
            "RTD_CS_N",
            "RTD_DRDY",
            "RTD_HW_FAULT",
            "SHARED_REF_2V5",
        ];
        if self.interface.pins.len() != expected_nets.len()
            || self
                .interface
                .pins
                .iter()
                .zip(expected_nets)
                .any(|(pin, net)| pin.number == 0 || pin.net != net)
        {
            errors.push("unit interface must expose the ordered ten-net boundary".into());
        }
        let mut pin_numbers = std::collections::BTreeSet::new();
        for pin in &self.interface.pins {
            if !(1..=10).contains(&pin.number) || !pin_numbers.insert(pin.number) {
                errors.push("unit interface pin numbers must be unique 1..=10".into());
            }
        }
        match (
            &self.interface.connector_mpn,
            self.interface.qualification_status.as_str(),
        ) {
            (None, "pending_qualified_source") => {}
            (Some(mpn), "qualified_source") if !mpn.trim().is_empty() => {}
            _ => errors
                .push("connector qualification must be pending or a qualified MPN/source".into()),
        }
        if self.probe.component.trim().is_empty()
            || self.probe.mpn.trim().is_empty()
            || self.probe.pins.len() != 4
        {
            errors.push("unit probe connector contract must contain four qualified pins".into());
        }
        if self.local.reference_component.trim().is_empty()
            || self.local.ferrite_component.trim().is_empty()
            || self.local.filtered_rail != "RTD_AVDD"
        {
            errors.push("unit local reference and filtered ferrite roles are required".into());
        }
        let b = &self.board;
        if b.copper_layers != 4
            || b.min_finished_copper_um != 35.0
            || b.clearance_mm != 0.20
            || b.signal_width_mm != 0.20
            || b.power_return_width_mm != 0.20
            || b.via_diameter_mm != 0.70
            || b.via_drill_mm != 0.30
        {
            errors.push("unit manufacturing contract does not match the standalone profile".into());
        }
        if !self.loads.iter().any(|load| {
            load.name == "RTD_LOCAL_10MA"
                && load.current_a == Some(0.01)
                && load.status == "pending_source_budget"
        }) {
            errors.push(
                "unit must declare the authored 10 mA budget as pending source load qualification"
                    .into(),
            );
        }
        if self.future_contracts.reference_consumers != "required_source_load_budget"
            || self.future_contracts.model != "required_fault_model"
        {
            errors.push("unit reference-load budget and fault model are mandatory inputs".into());
        }
        if self.decoupling_bindings.len() < 3
            || !self
                .decoupling_bindings
                .iter()
                .any(|d| (d.role == "adc_dvdd" || d.role == "adc_vdd") && d.capacitance_nf == 100.0)
            || !self
                .decoupling_bindings
                .iter()
                .any(|d| d.role == "rtd_input_filter" && d.capacitance_nf == 1.0)
        {
            errors.push(
                "unit must separate ADC supply decoupling from 1 nF RTD input filtering".into(),
            );
        }
        if self.return_planes.len() < 4
            || self.return_planes.iter().any(|plane| {
                plane.purpose.trim().is_empty()
                    || plane.net.trim().is_empty()
                    || !matches!(plane.layer.as_str(), "F.Cu" | "B.Cu" | "In1.Cu" | "In2.Cu")
            })
        {
            errors.push(
                "unit return-plane contract must name the four source-derived net/layer roles"
                    .into(),
            );
        }
        if self.fault_latency_limit_ms <= 0.0
            || !self.fault_latency_limit_ms.is_finite()
            || self.fault_latency_limit_ms >= 100.0
        {
            errors.push("unit fault latency limit must be finite and strictly below 100 ms".into());
        }
        errors
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn profile() -> UnitProfile {
        serde_json::from_str(include_str!("../../../rtd/unit/profile.json"))
            .expect("standalone profile JSON parses")
    }

    #[test]
    fn standalone_profile_matches_source_and_manufacturing_contract() {
        assert!(profile().validate().is_empty());
    }

    #[test]
    fn connector_qualification_cannot_be_filled_by_fixture_mutation() {
        let mut value: serde_json::Value =
            serde_json::from_str(include_str!("../../../rtd/unit/profile.json")).unwrap();
        value["interface"]["qualification_status"] =
            serde_json::Value::String("pending_qualified_source".into());
        let mutated: UnitProfile = serde_json::from_value(value).unwrap();
        assert!(mutated
            .validate()
            .iter()
            .any(|error| error.contains("connector qualification")
                || error.contains("probe connector")));
    }

    #[test]
    fn deferred_contracts_cannot_be_reported_as_run() {
        let mut value: serde_json::Value =
            serde_json::from_str(include_str!("../../../rtd/unit/profile.json")).unwrap();
        value["future_contracts"]["model"] = serde_json::Value::String("scope_not_run".into());
        let mutated: UnitProfile = serde_json::from_value(value).unwrap();
        assert!(mutated
            .validate()
            .iter()
            .any(|error| error.contains("mandatory inputs")));
    }

    fn native() -> UnitNativeEvidence {
        let mut evidence: UnitNativeEvidence = serde_json::from_value(serde_json::json!({
            "board_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "extractor_sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            "copper_layer_count": 4,
            "components": [
                {"id":"rtd_pan.adc","mpn":"MAX31865AAP+","kind":"adc","position_mm":[1.0,1.0],"footprint_pads":[{"pad":"1","net":"GND","position_mm":[1.0,1.0],"size_mm":[0.3,0.3],"layers":["F.Cu"]}]},
                {"id":"rtd_pan.r_ref","mpn":"RG2012V-431-W-T1","kind":"resistor","position_mm":[2.0,1.0],"footprint_pads":[{"pad":"1","net":"GND","position_mm":[2.0,1.0],"size_mm":[0.3,0.3],"layers":["F.Cu"]}]}
                ,{"id":"rtd_pan.supervisor","mpn":"TPS389001DSER","kind":"supervisor","position_mm":[2.5,1.0],"footprint_pads":[{"pad":"1","net":"GND","position_mm":[2.5,1.0],"size_mm":[0.3,0.3],"layers":["F.Cu"]}]}
            ],
            "connections": [{"component":"rtd_pan.adc","pin":"1","net":"GND"}],
            "connectivity_clusters": [{"net":"GND","nodes":["rtd_pan.adc.1"],"source":"native"}],
            "traces": [],
            "vias": []
        }))
        .unwrap();
        for (id, mpn, p1, n1, p2, n2) in [
            ("rtd_pan.c_vdd", "C0603C104K5RACTU", "1", "+3V3", "2", "GND"),
            (
                "rtd_pan.c_rtd_input",
                "C0603C102J5GACTU",
                "1",
                "RTDIN_P",
                "2",
                "RTDIN_N",
            ),
        ] {
            evidence.components.push(Component {
                id: id.into(),
                mpn: mpn.into(),
                kind: "capacitor".into(),
                position_mm: vec![3.0, 1.0],
                footprint_pads: vec![
                    crate::Pad {
                        pad: p1.into(),
                        net: n1.into(),
                        position_mm: [3.0, 1.0],
                        size_mm: [0.3, 0.3],
                        layers: vec!["F.Cu".into()],
                        orientation_deg: 0.0,
                    },
                    crate::Pad {
                        pad: p2.into(),
                        net: n2.into(),
                        position_mm: [3.5, 1.0],
                        size_mm: [0.3, 0.3],
                        layers: vec!["F.Cu".into()],
                        orientation_deg: 0.0,
                    },
                ],
            });
            evidence.connections.extend([
                Connection {
                    component: id.into(),
                    pin: p1.into(),
                    net: n1.into(),
                },
                Connection {
                    component: id.into(),
                    pin: p2.into(),
                    net: n2.into(),
                },
            ]);
            evidence.connectivity_clusters.extend([
                ConnectivityCluster {
                    net: n1.into(),
                    nodes: vec![format!("{id}.{p1}")],
                    source: "native".into(),
                },
                ConnectivityCluster {
                    net: n2.into(),
                    nodes: vec![format!("{id}.{p2}")],
                    source: "native".into(),
                },
            ]);
        }
        evidence
    }

    #[test]
    fn typed_unit_input_rejects_incomplete_unit_native_transport() {
        let input = UnitInput {
            schema: "zapote.rtd.unit-input.v1".into(),
            profile: profile(),
            native: native(),
            identity: UnitIdentity {
                profile_sha256: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
                    .into(),
                native_export_sha256:
                    "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb".into(),
                source_manifest_sha256:
                    "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc".into(),
                extractor_sha256:
                    "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb".into(),
                model_sha256: "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"
                    .into(),
                firmware_sha256: "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"
                    .into(),
                firmware_pins_sha256:
                    "1111111111111111111111111111111111111111111111111111111111111111".into(),
                board_sha256: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
                    .into(),
                binary_sha256: None,
            },
            firmware: UnitFirmwareEvidence {
                cs_gpio: 10,
                drdy_gpio: 9,
                low_threshold_word: 1526,
                high_threshold_word: 45722,
                short_fault_ohm: 10.0,
                open_fault_ohm: 300.0,
            },
            model: serde_json::json!({"faults":[{"name":"open","class":"open"}]}),
            model_qualification: None,
            source_bindings: Vec::new(),
            source_components: Vec::new(),
        };
        assert!(input
            .validate()
            .iter()
            .any(|error| error.contains("c_dvdd")));
    }

    #[test]
    fn typed_unit_input_rejects_duplicate_native_components() {
        let mut evidence = native();
        evidence.components.push(evidence.components[0].clone());
        let input = UnitInput {
            schema: "zapote.rtd.unit-input.v1".into(),
            profile: profile(),
            native: evidence,
            identity: UnitIdentity {
                profile_sha256: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
                    .into(),
                native_export_sha256:
                    "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb".into(),
                source_manifest_sha256:
                    "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc".into(),
                extractor_sha256:
                    "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb".into(),
                model_sha256: "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"
                    .into(),
                firmware_sha256: "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"
                    .into(),
                firmware_pins_sha256:
                    "1111111111111111111111111111111111111111111111111111111111111111".into(),
                board_sha256: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
                    .into(),
                binary_sha256: None,
            },
            firmware: UnitFirmwareEvidence {
                cs_gpio: 10,
                drdy_gpio: 9,
                low_threshold_word: 1526,
                high_threshold_word: 45722,
                short_fault_ohm: 10.0,
                open_fault_ohm: 300.0,
            },
            model: serde_json::json!({"faults":[{"name":"open","class":"open"}]}),
            model_qualification: None,
            source_bindings: Vec::new(),
            source_components: Vec::new(),
        };
        assert!(input
            .validate()
            .iter()
            .any(|error| error.contains("duplicate native component")));
    }
}
