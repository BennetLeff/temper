//! Typed, fail-closed input and finding model for Zapote RTD validation.

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

pub mod unit;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Identity {
    pub source_revision: String,
    pub source_hash: String,
    pub board_revision: String,
    pub board_hash: String,
    pub suite_revision: String,
    pub suite_hash: String,
    pub model_revision: String,
    pub model_hash: String,
    pub observed_source_hash: String,
    pub observed_board_hash: String,
    pub observed_suite_hash: String,
    pub observed_model_hash: String,
    #[serde(default)]
    pub native_export_sha256: Option<String>,
    #[serde(default)]
    pub native_board_sha256: Option<String>,
    #[serde(default)]
    pub native_extractor_sha256: Option<String>,
    #[serde(default)]
    pub native_binding_required: bool,
    pub runtime: String,
    pub provider: String,
}

impl Identity {
    pub fn validate(&self) -> Vec<String> {
        let mut errors = Vec::new();
        for (name, value) in [
            ("source_revision", &self.source_revision),
            ("source_hash", &self.source_hash),
            ("board_revision", &self.board_revision),
            ("board_hash", &self.board_hash),
            ("suite_revision", &self.suite_revision),
            ("suite_hash", &self.suite_hash),
            ("model_revision", &self.model_revision),
            ("model_hash", &self.model_hash),
            ("observed_source_hash", &self.observed_source_hash),
            ("observed_board_hash", &self.observed_board_hash),
            ("observed_suite_hash", &self.observed_suite_hash),
            ("observed_model_hash", &self.observed_model_hash),
            ("runtime", &self.runtime),
            ("provider", &self.provider),
        ] {
            if value.trim().is_empty() {
                errors.push(format!("identity.{name} is required"));
            }
        }
        for (name, value) in [
            ("source_hash", &self.source_hash),
            ("board_hash", &self.board_hash),
            ("suite_hash", &self.suite_hash),
            ("model_hash", &self.model_hash),
            ("observed_source_hash", &self.observed_source_hash),
            ("observed_board_hash", &self.observed_board_hash),
            ("observed_suite_hash", &self.observed_suite_hash),
            ("observed_model_hash", &self.observed_model_hash),
        ] {
            if !is_sha256(value) {
                errors.push(format!(
                    "identity.{name} must be a 64 character SHA-256 hex digest"
                ));
            }
        }
        for (claimed_name, claimed, observed_name, observed) in [
            (
                "source_hash",
                &self.source_hash,
                "observed_source_hash",
                &self.observed_source_hash,
            ),
            (
                "board_hash",
                &self.board_hash,
                "observed_board_hash",
                &self.observed_board_hash,
            ),
            (
                "suite_hash",
                &self.suite_hash,
                "observed_suite_hash",
                &self.observed_suite_hash,
            ),
            (
                "model_hash",
                &self.model_hash,
                "observed_model_hash",
                &self.observed_model_hash,
            ),
        ] {
            if claimed != observed {
                errors.push(format!(
                    "identity.{observed_name} does not match claimed {claimed_name}"
                ));
            }
        }
        for (name, value) in [
            ("native_export_sha256", &self.native_export_sha256),
            ("native_board_sha256", &self.native_board_sha256),
            ("native_extractor_sha256", &self.native_extractor_sha256),
        ] {
            if let Some(value) = value {
                if !is_sha256(value) {
                    errors.push(format!(
                        "identity.{name} must be a 64 character SHA-256 hex digest"
                    ));
                }
            }
        }
        if let Some(native_board_hash) = &self.native_board_sha256 {
            if native_board_hash != &self.board_hash {
                errors.push(
                    "identity.native_board_sha256 does not match current identity.board_hash"
                        .into(),
                );
            }
        }
        if self.native_binding_required
            && (self.native_export_sha256.is_none()
                || self.native_board_sha256.is_none()
                || self.native_extractor_sha256.is_none())
        {
            errors.push(
                "native binding requires export, extraction-board, and extractor hashes".into(),
            );
        }
        errors
    }
}

pub fn is_sha256(value: &str) -> bool {
    value.len() == 64 && value.bytes().all(|b| b.is_ascii_hexdigit())
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RunInput {
    pub schema_version: u32,
    pub identity: Identity,
    pub board: Board,
    pub rtd: RtdContract,
    pub firmware: FirmwareContract,
    pub scenarios: Vec<FaultScenario>,
    /// Applicability selector. Empty/Top uses the integrated cooker contract;
    /// RTDUnit keeps the same checker context while omitting absent hosts.
    #[serde(default)]
    pub applicability: String,
}

impl RunInput {
    pub fn validate(&self) -> Vec<String> {
        let mut errors = self.identity.validate();
        if self.schema_version != 1 {
            errors.push(format!(
                "schema_version {} is unsupported; expected 1",
                self.schema_version
            ));
        }
        errors.extend(self.board.validate());
        if self.applicability != "RTDUnit" {
            errors.extend(self.rtd.validate(&self.board));
        }
        errors.extend(self.firmware.validate());
        // A standalone unit may run all source/topology and board geometry
        // rules before the independent fault-model receipt is available.
        // Fault coverage reports this missing applicability itself; it must
        // not suppress unrelated evidence.
        if self.scenarios.is_empty() && self.applicability != "RTDUnit" {
            errors.push("scenarios must contain at least one case".into());
        }
        errors
    }

    pub fn canonical_hash(&self) -> String {
        let bytes = serde_json::to_vec(self).expect("RunInput is serializable");
        let digest = Sha256::digest(bytes);
        digest.iter().map(|b| format!("{b:02x}")).collect()
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Board {
    pub components: Vec<Component>,
    pub nets: Vec<Net>,
    pub connections: Vec<Connection>,
    pub traces: Vec<Trace>,
    pub connectivity_clusters: Vec<ConnectivityCluster>,
    pub vias: Vec<Via>,
    #[serde(default)]
    pub zones: Vec<NativeZone>,
    #[serde(default)]
    pub paths: Vec<PathConstraint>,
    pub geometry: GeometryConstraints,
}

impl Board {
    pub fn validate(&self) -> Vec<String> {
        let mut errors = Vec::new();
        if self.components.is_empty() {
            errors.push("board.components is required".into());
        }
        if self.nets.is_empty() {
            errors.push("board.nets is required".into());
        }
        if self.connections.is_empty() {
            errors.push("board.connections is required".into());
        }
        if self.connectivity_clusters.is_empty() {
            errors.push(
                "board.connectivity_clusters is required (native copper connectivity evidence)"
                    .into(),
            );
        }
        let component_ids: std::collections::BTreeSet<_> =
            self.components.iter().map(|c| c.id.as_str()).collect();
        let net_names: std::collections::BTreeSet<_> =
            self.nets.iter().map(|n| n.name.as_str()).collect();
        for c in &self.components {
            if c.id.trim().is_empty() {
                errors.push("board component id is required".into());
            }
            if c.mpn.trim().is_empty() {
                errors.push(format!("component {} MPN is required", c.id));
            }
            if c.position_mm.len() != 2 || c.position_mm.iter().any(|v| !v.is_finite()) {
                errors.push(format!("component {} requires finite [x,y] position", c.id));
            }
            for pad in &c.footprint_pads {
                if !net_names.contains(pad.net.as_str()) {
                    errors.push(format!(
                        "pad {}.{} references unknown net {}",
                        c.id, pad.pad, pad.net
                    ));
                }
                if pad.position_mm.iter().any(|v| !v.is_finite())
                    || pad.size_mm.iter().any(|v| !v.is_finite() || *v <= 0.0)
                    || pad.layers.is_empty()
                {
                    errors.push(format!(
                        "pad {}.{} requires finite positive size/position and at least one layer",
                        c.id, pad.pad
                    ));
                }
            }
        }
        for n in &self.nets {
            if n.name.trim().is_empty() {
                errors.push("board net name is required".into());
            }
            if n.domain.trim().is_empty() {
                errors.push(format!("net {} domain is required", n.name));
            }
        }
        for c in &self.connections {
            if !component_ids.contains(c.component.as_str()) {
                errors.push(format!(
                    "connection references unknown component {}",
                    c.component
                ));
            }
            if !net_names.contains(c.net.as_str()) {
                errors.push(format!("connection references unknown net {}", c.net));
            }
        }
        let mut component_ids_seen = std::collections::BTreeSet::new();
        for c in &self.components {
            if !component_ids_seen.insert(c.id.as_str()) {
                errors.push(format!("duplicate component id {}", c.id));
            }
        }
        let mut net_names_seen = std::collections::BTreeSet::new();
        for n in &self.nets {
            if !net_names_seen.insert(n.name.as_str()) {
                errors.push(format!("duplicate net name {}", n.name));
            }
        }
        let mut pin_assignments = std::collections::BTreeSet::new();
        for c in &self.connections {
            if !pin_assignments.insert((c.component.as_str(), c.pin.as_str())) {
                errors.push(format!(
                    "duplicate assignment for {}.{}",
                    c.component, c.pin
                ));
            }
        }
        for trace in &self.traces {
            if !net_names.contains(trace.net.as_str()) {
                errors.push(format!("trace references unknown net {}", trace.net));
            }
            if trace.width_mm <= 0.0 || !trace.width_mm.is_finite() {
                errors.push(format!(
                    "trace {} width must be finite and positive",
                    trace.net
                ));
            }
            if trace.points_mm.len() < 2 || trace.points_mm.iter().flatten().any(|v| !v.is_finite())
            {
                errors.push(format!("trace {} requires two finite points", trace.net));
            }
        }
        for via in &self.vias {
            if !net_names.contains(via.net.as_str()) {
                errors.push(format!("via references unknown net {}", via.net));
            }
            if via.position_mm.iter().any(|v| !v.is_finite())
                || via.drill_mm <= 0.0
                || !via.drill_mm.is_finite()
            {
                errors.push(format!("via {} position/drill is invalid", via.net));
            }
            if via.from_layer == via.to_layer {
                errors.push(format!("via {} must span distinct layers", via.net));
            }
        }
        for cluster in &self.connectivity_clusters {
            if !net_names.contains(cluster.net.as_str()) {
                errors.push(format!(
                    "connectivity cluster references unknown net {}",
                    cluster.net
                ));
            }
            if cluster.nodes.is_empty() {
                errors.push(format!(
                    "connectivity cluster {} has no native nodes",
                    cluster.net
                ));
            }
        }
        let mut zone_ids = std::collections::BTreeSet::new();
        for zone in &self.zones {
            if zone.id.trim().is_empty() || !zone_ids.insert(zone.id.as_str()) {
                errors.push(format!("duplicate or empty native zone id {}", zone.id));
            }
            if !net_names.contains(zone.net.as_str()) {
                errors.push(format!("native zone references unknown net {}", zone.net));
            }
            if !matches!(zone.layer.as_str(), "F.Cu" | "B.Cu" | "In1.Cu" | "In2.Cu") {
                errors.push(format!(
                    "native zone {} uses unknown copper layer {}",
                    zone.id, zone.layer
                ));
            }
            for polygon in &zone.filled_polygons {
                if polygon.outer_mm.len() < 3
                    || polygon
                        .outer_mm
                        .iter()
                        .flatten()
                        .any(|value| !value.is_finite())
                    || polygon.holes_mm.iter().any(|hole| {
                        hole.len() < 3 || hole.iter().flatten().any(|value| !value.is_finite())
                    })
                {
                    errors.push(format!(
                        "native zone {} has invalid filled polygon",
                        zone.id
                    ));
                }
            }
        }
        if self.geometry.required_locality_mm <= 0.0
            || !self.geometry.required_locality_mm.is_finite()
        {
            errors.push("board.geometry.required_locality_mm must be finite and positive".into());
        }
        errors
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Component {
    pub id: String,
    pub mpn: String,
    pub kind: String,
    pub position_mm: Vec<f64>,
    #[serde(default)]
    pub footprint_pads: Vec<Pad>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Pad {
    pub pad: String,
    pub net: String,
    pub position_mm: [f64; 2],
    pub size_mm: [f64; 2],
    pub layers: Vec<String>,
    #[serde(default)]
    pub orientation_deg: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Net {
    pub name: String,
    pub domain: String,
    pub role: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Connection {
    pub component: String,
    pub pin: String,
    pub net: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Trace {
    #[serde(default, alias = "uuid")]
    pub id: String,
    pub net: String,
    pub points_mm: Vec<[f64; 2]>,
    pub layer: String,
    pub width_mm: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Via {
    #[serde(default, alias = "uuid")]
    pub id: String,
    pub net: String,
    pub position_mm: [f64; 2],
    pub from_layer: String,
    pub to_layer: String,
    pub drill_mm: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ConnectivityCluster {
    pub net: String,
    pub nodes: Vec<String>,
    pub source: String,
}

/// Native KiCad filled-zone transport.  The exporter supplies the exact
/// SHAPE_POLY_SET outer ring and holes; policy decides which net/layer is
/// required for an RTD return corridor.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct NativeZone {
    #[serde(alias = "uuid")]
    pub id: String,
    pub net: String,
    pub layer: String,
    pub filled_polygons: Vec<NativeFilledPolygon>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct NativeFilledPolygon {
    pub outer_mm: Vec<[f64; 2]>,
    #[serde(default)]
    pub holes_mm: Vec<Vec<[f64; 2]>>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PathConstraint {
    pub name: String,
    pub nets: Vec<String>,
    pub component_ids: Vec<String>,
    #[serde(default)]
    pub trace_ids: Vec<String>,
    #[serde(default)]
    pub via_ids: Vec<String>,
    #[serde(default)]
    pub pad_ids: Vec<String>,
    /// Physical load-side terminals that receive the selected route.
    #[serde(default)]
    pub terminal_pad_ids: Vec<String>,
    /// Physical trunk/pour junction terminals observed in the native census.
    #[serde(default)]
    pub junction_pad_ids: Vec<String>,
    /// Optional same-IC pad population for the separate 0.20 mm copper rule.
    #[serde(default)]
    pub clearance_pad_ids: Vec<String>,
    #[serde(default)]
    pub max_branch_current_a: Option<f64>,
    #[serde(default)]
    pub copper_thickness_um: Option<f64>,
    #[serde(default)]
    pub max_route_mm: Option<f64>,
    #[serde(default)]
    pub uses_buck_or_mcu_trunk: bool,
    #[serde(default)]
    pub uses_shared_spine: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GeometryConstraints {
    #[serde(default)]
    pub sensitive_nets: Vec<String>,
    #[serde(default)]
    pub aggressors: Vec<Aggressor>,
    #[serde(default)]
    pub prohibited_connections: Vec<ProhibitedConnection>,
    pub required_locality_mm: f64,
    #[serde(default)]
    pub return_planes: Vec<ReturnPlaneRequirement>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ReturnPlaneRequirement {
    pub purpose: String,
    pub net: String,
    pub layer: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Aggressor {
    pub net: String,
    pub region_mm: [f64; 4],
    pub min_distance_mm: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProhibitedConnection {
    pub first_net: String,
    pub second_net: String,
    pub reason: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RtdContract {
    pub connector: Connector,
    pub adc: Adc,
    pub rref: Rref,
    pub reference: Reference,
    pub local_rail: LocalRail,
    pub required_local_ics: Vec<LocalIc>,
    pub decoupling: Vec<Decoupling>,
    pub spi: Vec<SpiSignal>,
    #[serde(default)]
    pub mcu_pads: std::collections::BTreeMap<String, String>,
    pub fault_output: FaultOutput,
    #[serde(default)]
    pub downstream_reference_consumers: Vec<ReferenceConsumer>,
}

impl RtdContract {
    pub fn validate(&self, board: &Board) -> Vec<String> {
        let mut errors = Vec::new();
        if self.connector.pins.len() != 4 {
            errors.push("rtd.connector.pins must contain four pins".into());
        }
        if self.spi.is_empty() {
            errors.push("rtd.spi is required".into());
        }
        if self.decoupling.is_empty() {
            errors.push("rtd.decoupling is required".into());
        }
        if self.required_local_ics.len() < 7 {
            errors.push("rtd.required_local_ics must enumerate ADC, reference, and all five local fault/rail ICs".into());
        }
        if self.downstream_reference_consumers.len() < 2 {
            errors.push(
                "rtd.downstream_reference_consumers must name both downstream consumers".into(),
            );
        }
        if self.rref.resistance_ohm <= 0.0 || !self.rref.resistance_ohm.is_finite() {
            errors.push("rtd.rref.resistance_ohm must be positive".into());
        }
        if !(0.0..=100.0).contains(&self.rref.tolerance_pct) {
            errors.push("rtd.rref.tolerance_pct must be in [0,100]".into());
        }
        for net in [
            &self.local_rail.upstream_net,
            &self.local_rail.post_ferrite_net,
            &self.fault_output.net,
        ] {
            if !board.nets.iter().any(|n| &n.name == net) {
                errors.push(format!("required RTD net {net} is absent from board"));
            }
        }
        errors
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Connector {
    pub component: String,
    pub pins: Vec<ConnectorPin>,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ConnectorPin {
    pub number: u8,
    pub role: String,
    pub net: String,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Adc {
    pub component: String,
    pub mpn: String,
    pub pins: std::collections::BTreeMap<String, String>,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Rref {
    pub component: String,
    pub mpn: String,
    pub resistance_ohm: f64,
    pub tolerance_pct: f64,
    pub connections: [String; 2],
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Reference {
    pub component: String,
    pub mpn: String,
    pub v1_net: String,
    pub v2_net: String,
    pub ground_net: String,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LocalRail {
    pub upstream_net: String,
    pub post_ferrite_net: String,
    pub ferrite_component: String,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LocalIc {
    pub component: String,
    pub rail: String,
    pub ground: String,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Decoupling {
    pub component: String,
    pub ic: String,
    pub rail: String,
    pub ground: String,
    pub capacitance_uf: f64,
    pub position_mm: [f64; 2],
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SpiSignal {
    pub signal: String,
    pub mcu_pin: u16,
    pub adc_pin: String,
    pub series_component: String,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FaultOutput {
    pub net: String,
    pub active_level: String,
    pub pullup_rail: String,
    pub gate: String,
    pub consumers: Vec<String>,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ReferenceConsumer {
    pub name: String,
    pub net: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FirmwareContract {
    pub gpio: std::collections::BTreeMap<String, u16>,
    pub thresholds: Thresholds,
    pub config_revision: String,
}

impl FirmwareContract {
    pub fn validate(&self) -> Vec<String> {
        let mut errors = Vec::new();
        for signal in ["RTD_SCK", "RTD_SDI", "RTD_SDO", "RTD_CS_N", "RTD_DRDY"] {
            if !self.gpio.contains_key(signal) {
                errors.push(format!("firmware.gpio.{signal} is required"));
            }
        }
        if self.config_revision.trim().is_empty() {
            errors.push("firmware.config_revision is required".into());
        }
        if !self.thresholds.short_ohm.is_finite()
            || self.thresholds.short_ohm < 0.0
            || !self.thresholds.open_ohm.is_finite()
            || self.thresholds.open_ohm <= self.thresholds.short_ohm
            || self.thresholds.rref_ohm <= 0.0
            || !self.thresholds.rref_ohm.is_finite()
            || !(1..=15).contains(&self.thresholds.adc_bits)
            || self.thresholds.shift > 16 - self.thresholds.adc_bits
        {
            errors.push("firmware threshold encoding parameters are invalid (finite ordered thresholds, positive RREF, ADC bits 1..15, shift fitting 16-bit register)".into());
        }
        errors
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Thresholds {
    pub short_ohm: f64,
    pub open_ohm: f64,
    pub low_word: u16,
    pub high_word: u16,
    pub rref_ohm: f64,
    pub adc_bits: u8,
    pub shift: u8,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FaultScenario {
    pub name: String,
    pub resistance_ohm: Option<f64>,
    pub conductor_open: Option<String>,
    pub rail_loss: Option<String>,
    pub expected_class: String,
    pub expected_detected: bool,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum Status {
    Pass,
    Fail,
    Indeterminate,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Finding {
    pub rule: String,
    pub severity: String,
    pub status: Status,
    pub message: String,
    pub object: String,
    pub actual: Option<String>,
    pub required: Option<String>,
}

impl Finding {
    pub fn pass(rule: &str, message: impl Into<String>, object: impl Into<String>) -> Self {
        Self {
            rule: rule.into(),
            severity: "info".into(),
            status: Status::Pass,
            message: message.into(),
            object: object.into(),
            actual: None,
            required: None,
        }
    }

    pub fn fail(rule: &str, message: impl Into<String>, object: impl Into<String>) -> Self {
        Self {
            rule: rule.into(),
            severity: "error".into(),
            status: Status::Fail,
            message: message.into(),
            object: object.into(),
            actual: None,
            required: None,
        }
    }
    pub fn indeterminate(
        rule: &str,
        message: impl Into<String>,
        object: impl Into<String>,
    ) -> Self {
        Self {
            rule: rule.into(),
            severity: "warning".into(),
            status: Status::Indeterminate,
            message: message.into(),
            object: object.into(),
            actual: None,
            required: None,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CheckReport {
    pub status: Status,
    pub findings: Vec<Finding>,
    pub checked_rules: Vec<String>,
    pub coverage_gaps: Vec<String>,
}

impl CheckReport {
    pub fn from_findings(
        findings: Vec<Finding>,
        checked_rules: Vec<String>,
        coverage_gaps: Vec<String>,
    ) -> Self {
        let status = if findings.iter().any(|f| f.status == Status::Fail) {
            Status::Fail
        } else if findings.iter().any(|f| f.status == Status::Indeterminate)
            || !coverage_gaps.is_empty()
        {
            Status::Indeterminate
        } else {
            Status::Pass
        };
        Self {
            status,
            findings,
            checked_rules,
            coverage_gaps,
        }
    }
}
