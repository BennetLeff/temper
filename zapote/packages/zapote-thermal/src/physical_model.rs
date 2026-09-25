//! Physical bridge package/lead thermal model.
//!
//! This is a deliberately small, auditable thermal-network model that sits
//! beside the Gmsh/Elmer neck solves.  It models one bridge package node and
//! four shared lead/barrel/solder paths; package dissipation is injected once
//! at the package node and conductor Joule heating is injected once per neck.
//! Package construction details not established by the manufacturer remain
//! explicit unknowns and keep applicability indeterminate.

use anyhow::{ensure, Context, Result};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;

pub const CONTRACT_SCHEMA: &str = "zapote.bridge-physical-model.contract.v1";
pub const ASSESSMENT_SCHEMA: &str = "zapote.bridge-physical-model.assessment.v1";
pub const BRIDGE_MPN: &str = "GBU2510A";
pub const REVIEWED_SOURCE_SHA256: &str =
    "8bae78604e65be4d011c2989bbaddd9aab32b55fbdd40a79891aa8803f997794";
pub const REVIEWED_VF_MAX_V: f64 = 1.0;
pub const REVIEWED_VF_REFERENCE_A: f64 = 12.5;
pub const NETS: [&str; 4] = ["minus", "ac1", "ac2", "plus"];

fn default_board_temperature() -> f64 {
    80.0
}

fn default_vf_reference_current() -> f64 {
    12.5
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Range {
    pub nominal: f64,
    pub min: f64,
    pub max: f64,
    pub units: String,
    pub provenance: String,
    pub status: String,
}

impl Range {
    fn validate(&self, name: &str) -> Result<()> {
        for (label, value) in [
            ("nominal", self.nominal),
            ("min", self.min),
            ("max", self.max),
        ] {
            ensure!(
                value.is_finite() && value > 0.0,
                "{name}.{label} must be finite and positive"
            );
        }
        ensure!(
            self.min <= self.nominal && self.nominal <= self.max,
            "{name} range is not ordered"
        );
        ensure!(
            !self.units.is_empty() && !self.provenance.is_empty(),
            "{name} requires units and provenance"
        );
        ensure!(
            matches!(
                self.units.as_str(),
                "mm" | "mm2" | "um" | "W" | "S/m" | "W/K" | "V" | "ohm"
            ),
            "{name} has unsupported units"
        );
        ensure!(
            matches!(
                self.status.as_str(),
                "sourced" | "assembly_assumption" | "unknown"
            ),
            "{name} has invalid status"
        );
        Ok(())
    }

    fn validate_units(&self, name: &str, expected: &str) -> Result<()> {
        self.validate(name)?;
        ensure!(self.units == expected, "{name} must use units {expected}");
        Ok(())
    }
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct LeadPath {
    pub net: String,
    pub pad_uuid: String,
    pub trace_uuid: String,
    pub trace_length_mm: Range,
    pub trace_width_mm: Range,
    pub copper_thickness_um: Range,
    pub lead_length_mm: Range,
    pub lead_cross_section_mm2: Range,
    pub barrel_length_mm: Range,
    pub barrel_inner_diameter_mm: Range,
    pub barrel_plating_mm: Range,
    pub solder_thickness_mm: Range,
    pub solder_area_mm2: Range,
}

impl LeadPath {
    fn validate(&self) -> Result<()> {
        ensure!(
            NETS.contains(&self.net.as_str()),
            "unsupported bridge neck net {}",
            self.net
        );
        ensure!(
            !self.pad_uuid.is_empty() && !self.trace_uuid.is_empty(),
            "lead path identity is required"
        );
        for (name, value, units) in [
            ("trace_length_mm", &self.trace_length_mm, "mm"),
            ("trace_width_mm", &self.trace_width_mm, "mm"),
            ("copper_thickness_um", &self.copper_thickness_um, "um"),
            ("lead_length_mm", &self.lead_length_mm, "mm"),
            (
                "lead_cross_section_mm2",
                &self.lead_cross_section_mm2,
                "mm2",
            ),
            ("barrel_length_mm", &self.barrel_length_mm, "mm"),
            (
                "barrel_inner_diameter_mm",
                &self.barrel_inner_diameter_mm,
                "mm",
            ),
            ("barrel_plating_mm", &self.barrel_plating_mm, "mm"),
            ("solder_thickness_mm", &self.solder_thickness_mm, "mm"),
            ("solder_area_mm2", &self.solder_area_mm2, "mm2"),
        ] {
            value.validate_units(name, units)?;
        }
        ensure!(
            self.barrel_plating_mm.max * 2.0 < self.barrel_inner_diameter_mm.min,
            "barrel plating closes the bore"
        );
        Ok(())
    }

    /// Compute a deliberately conservative lumped sensitivity resistance.
    ///
    /// This sums nominal trace, lead, barrel and solder terms in series. It
    /// is useful for screening the network's Joule-source magnitude, but it
    /// is not an electrical validation of the real joint: barrel plating,
    /// solder wetting and lead/contact paths can be parallel and distributed.
    /// The joint-terminal FEM must replace this value before a thermal result
    /// is treated as a physical acceptance claim.
    fn nominal_resistance_ohm(
        &self,
        conductivity_s_m: f64,
        solder_conductivity_s_m: f64,
    ) -> Result<f64> {
        let trace = self.trace_length_mm.nominal * 1e-3
            / (conductivity_s_m
                * self.trace_width_mm.nominal
                * 1e-3
                * self.copper_thickness_um.nominal
                * 1e-6);
        let lead = self.lead_length_mm.nominal * 1e-3
            / (conductivity_s_m * self.lead_cross_section_mm2.nominal * 1e-6);
        let ro =
            (self.barrel_inner_diameter_mm.nominal * 0.5 + self.barrel_plating_mm.nominal) * 1e-3;
        let ri = self.barrel_inner_diameter_mm.nominal * 0.5e-3;
        let barrel_area = std::f64::consts::PI * (ro * ro - ri * ri);
        ensure!(barrel_area > 0.0, "barrel annulus area is not positive");
        let barrel = self.barrel_length_mm.nominal * 1e-3 / (conductivity_s_m * barrel_area);
        let solder = self.solder_thickness_mm.nominal * 1e-3
            / (solder_conductivity_s_m * self.solder_area_mm2.nominal * 1e-6);
        let resistance = trace + lead + barrel + solder;
        ensure!(
            resistance.is_finite() && resistance > 0.0,
            "lead path resistance is invalid"
        );
        Ok(resistance)
    }
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct LossInput {
    pub bridge_mpn: String,
    pub source_url: String,
    pub source_sha256: Option<String>,
    pub source_status: String,
    pub forward_voltage_v_at_12_5a: Range,
    /// Current at which the archived forward-voltage point was specified.
    /// An optional slope is applied about this point, avoiding a second
    /// intercept being added to the manufacturer value.
    #[serde(default = "default_vf_reference_current")]
    pub vf_reference_current_a: f64,
    pub dynamic_resistance_ohm: Option<Range>,
    /// Number of physical diodes conducting at one instant (two for a
    /// full-wave bridge). This multiplies the pair-loss expression; it is not
    /// the total number of package elements for junction-rating purposes.
    pub conducting_diode_count: u8,
    pub pfc_profile_sha256: Option<String>,
}

impl LossInput {
    fn validate(&self) -> Result<()> {
        ensure!(self.bridge_mpn == BRIDGE_MPN, "unsupported bridge MPN");
        ensure!(
            !self.source_url.is_empty(),
            "bridge loss source URL is required"
        );
        ensure!(
            matches!(
                self.source_status.as_str(),
                "byte_archived" | "cached_primary_text" | "unavailable"
            ),
            "invalid bridge loss source status"
        );
        self.forward_voltage_v_at_12_5a
            .validate_units("forward_voltage_v_at_12_5a", "V")?;
        ensure!(
            self.vf_reference_current_a.is_finite() && self.vf_reference_current_a > 0.0,
            "VF reference current must be finite and positive"
        );
        if let Some(dynamic) = &self.dynamic_resistance_ohm {
            dynamic.validate_units("dynamic_resistance_ohm", "ohm")?;
        }
        if let Some(hash) = &self.source_sha256 {
            ensure!(
                hash.len() == 64 && hash.bytes().all(|b| b.is_ascii_hexdigit()),
                "invalid bridge source hash"
            );
            if self.source_status == "byte_archived" {
                ensure!(
                    hash == REVIEWED_SOURCE_SHA256,
                    "bridge source digest is not reviewed"
                );
                ensure!(
                    self.vf_reference_current_a == REVIEWED_VF_REFERENCE_A
                        && self.forward_voltage_v_at_12_5a.nominal == REVIEWED_VF_MAX_V
                        && self.forward_voltage_v_at_12_5a.max == REVIEWED_VF_MAX_V,
                    "bridge VF point is not the reviewed source point"
                );
            }
        } else {
            ensure!(
                self.source_status != "byte_archived",
                "byte_archived bridge source requires a SHA-256 identity"
            );
        }
        ensure!(
            self.conducting_diode_count == 2,
            "bridge model requires the two conducting diode count"
        );
        if let Some(hash) = &self.pfc_profile_sha256 {
            ensure!(
                hash.len() == 64 && hash.bytes().all(|b| b.is_ascii_hexdigit()),
                "invalid PFC profile hash"
            );
        }
        Ok(())
    }

    /// Verify the archived manufacturer bytes before treating a source as
    /// byte-bound. A hash-shaped string in JSON is not evidence by itself.
    pub fn validate_source_bytes(&self, bytes: &[u8]) -> Result<()> {
        let expected = self
            .source_sha256
            .as_deref()
            .context("source bytes cannot be verified without source_sha256")?;
        let actual = format!("{:x}", Sha256::digest(bytes));
        ensure!(
            actual == expected,
            "archived bridge source bytes do not match source_sha256"
        );
        ensure!(
            actual == REVIEWED_SOURCE_SHA256,
            "archived bridge source digest is not reviewed"
        );
        // This digest identifies the independently reviewed PDF, including
        // compressed streams. Plaintext searches in PDF bytes are not text
        // extraction and reject the genuine document's compressed VF table.
        Ok(())
    }
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct PhysicalModelContract {
    pub schema: String,
    pub board_sha256: String,
    /// Digest of the extracted four-neck geometry. Optional only for the
    /// historical v1 fixture; reviewed variants must populate it.
    #[serde(default)]
    pub geometry_sha256: Option<String>,
    pub bridge_mpn: String,
    pub bridge_loss_allowance_w: Range,
    pub ambient_c: f64,
    pub sink_c: f64,
    /// Fixed board reservoir used by the lead/barrel/solder paths.  This is
    /// deliberately separate from the cooled sink: the board can be hotter
    /// than the heatsink and must not disappear from the KCL system.
    #[serde(default = "default_board_temperature")]
    pub board_c: f64,
    pub copper_conductivity_s_m: Range,
    pub solder_conductivity_s_m: Range,
    pub package_to_sink_w_per_k: Range,
    pub lead_to_package_w_per_k: Range,
    pub lead_to_board_w_per_k: Range,
    pub junction_limit_c: f64,
    pub pcb_limit_c: f64,
    pub loss: LossInput,
    pub paths: Vec<LeadPath>,
}

impl PhysicalModelContract {
    pub fn validate(&self, board_sha256: &str) -> Result<()> {
        ensure!(
            self.schema == CONTRACT_SCHEMA,
            "unsupported physical-model contract schema"
        );
        ensure!(
            self.board_sha256 == board_sha256
                && self.board_sha256.len() == 64
                && self.board_sha256.bytes().all(|b| b.is_ascii_hexdigit()),
            "physical-model board identity mismatch"
        );
        if let Some(hash) = &self.geometry_sha256 {
            ensure!(
                hash.len() == 64 && hash.bytes().all(|b| b.is_ascii_hexdigit()),
                "invalid physical-model geometry hash"
            );
        }
        ensure!(self.bridge_mpn == BRIDGE_MPN, "unsupported bridge package");
        for (name, value) in [
            ("bridge_loss_allowance_w", &self.bridge_loss_allowance_w),
            ("copper_conductivity_s_m", &self.copper_conductivity_s_m),
            ("solder_conductivity_s_m", &self.solder_conductivity_s_m),
            ("package_to_sink_w_per_k", &self.package_to_sink_w_per_k),
            ("lead_to_package_w_per_k", &self.lead_to_package_w_per_k),
            ("lead_to_board_w_per_k", &self.lead_to_board_w_per_k),
        ] {
            let units = match name {
                "bridge_loss_allowance_w" => "W",
                "copper_conductivity_s_m" | "solder_conductivity_s_m" => "S/m",
                "package_to_sink_w_per_k" | "lead_to_package_w_per_k" | "lead_to_board_w_per_k" => {
                    "W/K"
                }
                _ => unreachable!("all contract ranges have explicit units"),
            };
            value.validate_units(name, units)?;
        }
        ensure!(
            self.ambient_c.is_finite()
                && self.sink_c.is_finite()
                && self.board_c.is_finite()
                && self.ambient_c > 0.0
                && self.sink_c >= self.ambient_c,
            "thermal boundaries are invalid"
        );
        ensure!(
            self.board_c >= self.ambient_c,
            "board reservoir is below ambient"
        );
        ensure!(
            self.junction_limit_c.is_finite()
                && self.pcb_limit_c.is_finite()
                && self.junction_limit_c <= 125.0
                && self.pcb_limit_c <= 110.0,
            "thermal limits relax fixed ceilings"
        );
        ensure!(
            self.paths.len() == 4,
            "physical model requires four bridge lead paths"
        );
        let mut nets = std::collections::BTreeSet::new();
        for path in &self.paths {
            path.validate()?;
            ensure!(
                nets.insert(path.net.clone()),
                "duplicate bridge lead path net"
            );
        }
        let expected: std::collections::BTreeSet<_> = NETS.into_iter().map(str::to_owned).collect();
        ensure!(
            nets == expected,
            "physical model must cover minus/ac1/ac2/plus"
        );
        self.loss.validate()
    }
}

#[derive(Clone, Copy, Debug, Serialize, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct WaveformSample {
    pub weight: f64,
    pub line_sign: f64,
    pub inductor_a: f64,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct WaveformInput {
    pub profile_sha256: String,
    pub samples: Vec<WaveformSample>,
    pub neck_rms_a: BTreeMap<String, f64>,
}

impl WaveformInput {
    pub fn validate(&self) -> Result<()> {
        ensure!(
            self.profile_sha256.len() == 64
                && self.profile_sha256.bytes().all(|b| b.is_ascii_hexdigit()),
            "invalid waveform profile hash"
        );
        ensure!(!self.samples.is_empty(), "PFC waveform is empty");
        let mut weight_sum = 0.0;
        for sample in &self.samples {
            ensure!(
                sample.weight.is_finite()
                    && sample.weight >= 0.0
                    && sample.line_sign.is_finite()
                    && sample.inductor_a.is_finite()
                    && sample.inductor_a >= 0.0,
                "invalid PFC waveform sample"
            );
            weight_sum += sample.weight;
        }
        ensure!(
            (weight_sum - 1.0).abs() <= 1e-9,
            "PFC waveform weights do not sum to one"
        );
        for net in NETS {
            let current = self
                .neck_rms_a
                .get(net)
                .copied()
                .context("missing PFC bridge neck RMS")?;
            ensure!(
                current.is_finite() && current > 0.0,
                "invalid PFC bridge neck RMS"
            );
        }
        Ok(())
    }
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct NeckResult {
    pub net: String,
    pub rms_current_a: f64,
    /// Lumped screening resistance; not a validated package-joint value.
    pub path_resistance_ohm: f64,
    pub joule_power_w: f64,
    pub temperature_c: f64,
    pub package_to_lead_w: f64,
    pub lead_to_board_w: f64,
    pub lead_power_residual_w: f64,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Assessment {
    pub schema: String,
    pub status: String,
    pub board_sha256: String,
    pub contract_sha256: String,
    pub waveform_sha256: String,
    /// False until the archived manufacturer bytes have been supplied to
    /// `LossInput::validate_source_bytes`; source URL/hash metadata alone is
    /// never promoted to a verified source binding.
    #[serde(default)]
    pub source_bytes_verified: bool,
    pub diode_loss_w: f64,
    pub package_heat_w: f64,
    pub unallocated_package_heat_w: f64,
    pub total_conductor_heat_w: f64,
    pub global_power_residual_w: f64,
    pub package_temperature_c: f64,
    pub board_temperature_c: f64,
    pub sink_temperature_c: f64,
    pub package_to_sink_w: f64,
    pub package_to_leads_w: f64,
    pub leads_to_board_w: f64,
    pub global_heat_input_w: f64,
    pub global_heat_output_w: f64,
    pub necks: Vec<NeckResult>,
    pub numerical_valid: bool,
    pub applicability: String,
    pub limitations: Vec<String>,
}

/// Hash exactly the serialized waveform input used by the loss calculation.
pub fn waveform_sha256(input: &WaveformInput) -> Result<String> {
    input.validate()?;
    Ok(format!("{:x}", Sha256::digest(serde_json::to_vec(input)?)))
}

/// Bind the contract's path UUIDs and dimensions to a fresh native extraction.
pub fn validate_geometry_binding(
    contract: &PhysicalModelContract,
    model: &crate::neck_geometry::NeckModel,
) -> Result<()> {
    ensure!(
        contract.board_sha256 == model.board_sha256,
        "physical-model geometry board mismatch"
    );
    if let Some(expected) = &contract.geometry_sha256 {
        ensure!(
            expected == &crate::neck_geometry::geometry_fingerprint(model)?,
            "physical-model geometry fingerprint mismatch"
        );
    }
    ensure!(
        contract.paths.len() == model.necks.len(),
        "physical-model path count mismatch"
    );
    for (path, neck) in contract.paths.iter().zip(&model.necks) {
        ensure!(
            path.net == neck.net
                && path.pad_uuid == neck.pad_uuid
                && path.trace_uuid == neck.trace_uuid
                && (path.trace_length_mm.nominal - neck.trace_length_mm).abs() < 1e-6
                && (path.trace_width_mm.nominal - neck.trace_width_mm).abs() < 1e-9
                // The contract's barrel bore is the plated through-hole
                // inner diameter extracted from the native pad drill.
                && (path.barrel_inner_diameter_mm.nominal - neck.drill_mm).abs() < 1e-9,
            "physical-model path does not match native geometry for {}",
            path.net
        );
    }
    Ok(())
}

/// Evaluate the shared package network and source-bound bridge diode loss.
pub fn evaluate(contract: &PhysicalModelContract, waveform: &WaveformInput) -> Result<Assessment> {
    contract.validate(&contract.board_sha256)?;
    waveform.validate()?;
    let waveform_hash = waveform_sha256(waveform)?;
    if let Some(expected) = &contract.loss.pfc_profile_sha256 {
        ensure!(
            expected == &waveform_hash,
            "PFC waveform does not match physical-model contract"
        );
    }
    let mut mean_i = 0.0;
    let mut mean_i2 = 0.0;
    for sample in &waveform.samples {
        let i = sample.inductor_a;
        mean_i += sample.weight * i;
        mean_i2 += sample.weight * i * i;
    }
    let vf = contract.loss.forward_voltage_v_at_12_5a.nominal;
    let rd = contract
        .loss
        .dynamic_resistance_ohm
        .as_ref()
        .map(|r| r.nominal)
        .unwrap_or(0.0);
    // The archived VF is specified at Iref=12.5 A.  If a dynamic slope is
    // supplied, apply V(i)=Vref+rd*(i-Iref), using the waveform's weighted
    // first and second moments.  This avoids the common but incorrect
    // `Vref*I + rd*I²` double-intercept calculation.
    let diode_pair_power =
        mean_i * vf + rd * (mean_i2 - contract.loss.vf_reference_current_a * mean_i);
    ensure!(
        diode_pair_power.is_finite() && diode_pair_power >= 0.0,
        "diode loss model produced a negative or non-finite power"
    );
    let diode_loss = f64::from(contract.loss.conducting_diode_count) * diode_pair_power;
    ensure!(
        diode_loss.is_finite() && diode_loss >= 0.0,
        "diode loss is invalid"
    );
    let package_heat = contract.bridge_loss_allowance_w.nominal;
    ensure!(
        package_heat >= diode_loss,
        "source-bound diode loss exceeds package allowance"
    );
    let unallocated = package_heat - diode_loss;
    let mut necks = Vec::with_capacity(4);
    let mut total_conductor = 0.0;
    let mut resistances = Vec::with_capacity(4);
    let mut joule_powers = Vec::with_capacity(4);
    for path in &contract.paths {
        let current = waveform.neck_rms_a[&path.net];
        let resistance = path.nominal_resistance_ohm(
            contract.copper_conductivity_s_m.nominal,
            contract.solder_conductivity_s_m.nominal,
        )?;
        let joule = current * current * resistance;
        total_conductor += joule;
        resistances.push(resistance);
        joule_powers.push(joule);
    }
    let package_to_sink = contract.package_to_sink_w_per_k.nominal;
    let lead_to_package = contract.lead_to_package_w_per_k.nominal;
    let lead_to_board = contract.lead_to_board_w_per_k.nominal;
    ensure!(
        package_to_sink > 0.0 && lead_to_package > 0.0 && lead_to_board > 0.0,
        "thermal network has no return path"
    );
    // Solve the five-node KCL system: one shared package node and one node
    // per physical lead.  The package source is injected once.  Each lead's
    // Joule source is injected once at that lead node, and its heat can flow
    // to either the package or the board reservoir.  Keeping these nodes in
    // one system prevents the old (incorrect) direct-sink shortcut from
    // bypassing the board conductance.
    let mut matrix = [[0.0_f64; 6]; 5];
    matrix[0][0] = package_to_sink + 4.0 * lead_to_package;
    matrix[0][5] = package_to_sink * contract.sink_c + package_heat;
    for (i, joule) in joule_powers.iter().enumerate() {
        let row = i + 1;
        matrix[0][row] = -lead_to_package;
        matrix[row][0] = -lead_to_package;
        matrix[row][row] = lead_to_package + lead_to_board;
        matrix[row][5] = lead_to_board * contract.board_c + *joule;
    }
    let temperatures = solve_linear_system(matrix)?;
    let package_temperature = temperatures[0];
    for (i, path) in contract.paths.iter().enumerate() {
        let lead_temperature = temperatures[i + 1];
        let package_to_lead = lead_to_package * (package_temperature - lead_temperature);
        let to_board = lead_to_board * (lead_temperature - contract.board_c);
        let lead_residual = joule_powers[i] + package_to_lead - to_board;
        necks.push(NeckResult {
            net: path.net.clone(),
            rms_current_a: waveform.neck_rms_a[&path.net],
            path_resistance_ohm: resistances[i],
            joule_power_w: joule_powers[i],
            temperature_c: lead_temperature,
            package_to_lead_w: package_to_lead,
            lead_to_board_w: to_board,
            lead_power_residual_w: lead_residual,
        });
    }
    let package_to_sink_w = package_to_sink * (package_temperature - contract.sink_c);
    let package_to_leads_w: f64 = necks.iter().map(|n| n.package_to_lead_w).sum();
    let leads_to_board_w: f64 = necks.iter().map(|n| n.lead_to_board_w).sum();
    let total_input = package_heat + total_conductor;
    let total_output = package_to_sink_w + leads_to_board_w;
    let residual = total_input - total_output;
    let numerical_valid = residual.abs() <= 1e-8 * (package_heat + total_conductor).max(1.0);
    ensure!(
        numerical_valid,
        "shared thermal network energy balance failed"
    );
    let applicability = if contract.loss.source_sha256.is_some()
        && contract.loss.source_status == "byte_archived"
        && contract.package_to_sink_w_per_k.status == "sourced"
        && contract.lead_to_package_w_per_k.status == "sourced"
        && contract.lead_to_board_w_per_k.status == "sourced"
        && contract.paths.iter().all(|p| {
            [
                &p.lead_length_mm,
                &p.lead_cross_section_mm2,
                &p.barrel_length_mm,
                &p.barrel_inner_diameter_mm,
                &p.barrel_plating_mm,
                &p.solder_thickness_mm,
                &p.solder_area_mm2,
            ]
            .iter()
            .all(|r| r.status == "sourced")
        }) {
        "conditional"
    } else {
        "indeterminate"
    };
    Ok(Assessment {
        schema: ASSESSMENT_SCHEMA.into(),
        status: "physical_model_numerical_only".into(),
        board_sha256: contract.board_sha256.clone(),
        contract_sha256: format!("{:x}", Sha256::digest(serde_json::to_vec(contract)?)),
        waveform_sha256: waveform_hash,
        source_bytes_verified: false,
        diode_loss_w: diode_loss,
        package_heat_w: package_heat,
        unallocated_package_heat_w: unallocated,
        total_conductor_heat_w: total_conductor,
        global_power_residual_w: residual,
        package_temperature_c: package_temperature,
        board_temperature_c: contract.board_c,
        sink_temperature_c: contract.sink_c,
        package_to_sink_w,
        package_to_leads_w,
        leads_to_board_w,
        global_heat_input_w: total_input,
        global_heat_output_w: total_output,
        necks,
        numerical_valid,
        applicability: applicability.into(),
        limitations: vec![
            "GBU2510A package internals and lead/barrel/solder heat split are not established by byte-archived source data.".into(),
            "The 40 W bridge allowance is retained as one shared package source; diode loss is reported inside it and never replicated per neck.".into(),
            "Lead and board temperatures are analytical network outputs, not hardware qualification.".into(),
        ],
    })
}

/// Evaluate after checking the archived manufacturer bytes. Only the pinned
/// reviewed source digest can promote `source_bytes_verified`.
pub fn evaluate_with_source_bytes(
    contract: &PhysicalModelContract,
    waveform: &WaveformInput,
    source_bytes: &[u8],
) -> Result<Assessment> {
    contract.loss.validate_source_bytes(source_bytes)?;
    let mut assessment = evaluate(contract, waveform)?;
    assessment.source_bytes_verified = true;
    Ok(assessment)
}

pub fn replay(
    contract_bytes: &[u8],
    assessment_bytes: &[u8],
    board_sha256: &str,
    waveform: &WaveformInput,
) -> Result<Assessment> {
    let contract: PhysicalModelContract =
        serde_json::from_slice(contract_bytes).context("parse physical-model contract")?;
    contract.validate(board_sha256)?;
    let recorded: Assessment =
        serde_json::from_slice(assessment_bytes).context("parse physical-model assessment")?;
    ensure!(
        recorded.schema == ASSESSMENT_SCHEMA,
        "unsupported physical-model assessment schema"
    );
    ensure!(
        recorded.board_sha256 == board_sha256,
        "assessment board identity mismatch"
    );
    let hash = format!("{:x}", Sha256::digest(serde_json::to_vec(&contract)?));
    ensure!(
        recorded.contract_sha256 == hash,
        "assessment contract hash mismatch"
    );
    let expected_waveform = waveform_sha256(waveform)?;
    ensure!(
        recorded.waveform_sha256 == expected_waveform,
        "assessment waveform binding mismatch"
    );
    let fresh = evaluate(&contract, waveform)?;
    ensure!(
        fresh == recorded,
        "assessment does not match recomputed physical model"
    );
    Ok(fresh)
}

/// Replay variant that checks manufacturer source bytes before recomputing the
/// assessment. Only the pinned reviewed digest is accepted.
pub fn replay_with_source_bytes(
    contract_bytes: &[u8],
    assessment_bytes: &[u8],
    board_sha256: &str,
    waveform: &WaveformInput,
    source_bytes: &[u8],
) -> Result<Assessment> {
    let contract: PhysicalModelContract = serde_json::from_slice(contract_bytes)?;
    contract.validate(board_sha256)?;
    let expected = evaluate_with_source_bytes(&contract, waveform, source_bytes)?;
    let recorded: Assessment = serde_json::from_slice(assessment_bytes)?;
    ensure!(
        recorded.schema == ASSESSMENT_SCHEMA
            && recorded.board_sha256 == board_sha256
            && recorded.contract_sha256
                == format!("{:x}", Sha256::digest(serde_json::to_vec(&contract)?))
            && recorded.waveform_sha256 == waveform_sha256(waveform)?,
        "source-bound assessment identity mismatch"
    );
    ensure!(
        recorded == expected,
        "assessment does not match source-bound model"
    );
    Ok(expected)
}

/// Build a baseline contract from the reviewed native neck dimensions.
pub fn baseline_contract(
    board_sha256: impl Into<String>,
    model: &crate::neck_geometry::NeckModel,
) -> PhysicalModelContract {
    let paths = model
        .necks
        .iter()
        .map(|neck| LeadPath {
            net: neck.net.clone(),
            pad_uuid: neck.pad_uuid.clone(),
            trace_uuid: neck.trace_uuid.clone(),
            trace_length_mm: sourced_range(neck.trace_length_mm, "mm", "native extraction"),
            trace_width_mm: sourced_range(neck.trace_width_mm, "mm", "native extraction"),
            // This convenience constructor has no board bytes from which to
            // read stackup dimensions. Keep the nominal only as an explicit
            // sensitivity assumption; production callers must use
            // `contract_from_native`, which replaces it with parsed values.
            copper_thickness_um: unknown_range(
                70.0,
                "um",
                "native board stackup required; fallback sensitivity value",
            ),
            lead_length_mm: unknown_range(3.0, "mm", "GBU2510A internal lead geometry unavailable"),
            lead_cross_section_mm2: unknown_range(
                1.0,
                "mm2",
                "GBU2510A internal lead geometry unavailable",
            ),
            barrel_length_mm: unknown_range(
                1.6,
                "mm",
                "native board stackup required; fallback sensitivity value",
            ),
            barrel_inner_diameter_mm: sourced_range(neck.drill_mm, "mm", "native extraction"),
            barrel_plating_mm: unknown_range(0.025, "mm", "fabrication assumption"),
            solder_thickness_mm: unknown_range(0.2, "mm", "assembly assumption"),
            solder_area_mm2: unknown_range(
                neck.pad_size_mm[0] * neck.pad_size_mm[1],
                "mm2",
                "native pad envelope; wetting unknown",
            ),
        })
        .collect();
    PhysicalModelContract {
        schema: CONTRACT_SCHEMA.into(),
        board_sha256: board_sha256.into(),
        geometry_sha256: Some(
            crate::neck_geometry::geometry_fingerprint(model).expect("NeckModel is serializable"),
        ),
        bridge_mpn: BRIDGE_MPN.into(),
        bridge_loss_allowance_w: assumption_range(
            40.0,
            "W",
            "design allowance; package loss not source-bounded",
        ),
        ambient_c: 40.0,
        sink_c: 60.0,
        board_c: 80.0,
        copper_conductivity_s_m: sourced_range(5.5e7, "S/m", "copper nominal at 20 C"),
        solder_conductivity_s_m: unknown_range(5.0e6, "S/m", "solder alloy unspecified"),
        package_to_sink_w_per_k: unknown_range(
            1.0,
            "W/K",
            "package thermal path not source-bounded",
        ),
        lead_to_package_w_per_k: unknown_range(
            0.2,
            "W/K",
            "package lead coupling not source-bounded",
        ),
        lead_to_board_w_per_k: unknown_range(0.02, "W/K", "assembly heat path not measured"),
        junction_limit_c: 125.0,
        pcb_limit_c: 110.0,
        loss: LossInput {
            bridge_mpn: BRIDGE_MPN.into(),
            source_url:
                "https://www.21yangjie.com/pdf/zlqj/zhengliuqiao/GBU25005A%20THRU%20GBU2510A.pdf"
                    .into(),
            source_sha256: None,
            source_status: "cached_primary_text".into(),
            forward_voltage_v_at_12_5a: sourced_range(
                1.0,
                "V",
                "manufacturer cached primary text; VF max at IFM=12.5 A",
            ),
            vf_reference_current_a: 12.5,
            dynamic_resistance_ohm: None,
            conducting_diode_count: 2,
            pfc_profile_sha256: None,
        },
        paths,
    }
}

/// Build a source-bound physical-model contract directly from native and
/// manufacturing captures. This is the production bridge from KiCad export
/// data to the thermal model; callers must retain both input files alongside
/// the resulting contract.
pub fn contract_from_native(
    native_json: &[u8],
    manufacturing_json: &[u8],
) -> Result<PhysicalModelContract> {
    let model = crate::neck_geometry::build_neck_model_variant(native_json, manufacturing_json)?;
    let stackup = crate::neck_geometry::extract_stackup_dimensions(native_json)?;
    let mut contract = baseline_contract(model.board_sha256.clone(), &model);
    for path in &mut contract.paths {
        path.copper_thickness_um =
            sourced_range(stackup.copper_thickness_um, "um", "native board stackup");
        path.barrel_length_mm =
            sourced_range(stackup.board_thickness_mm, "mm", "native board stackup");
    }
    Ok(contract)
}

fn sourced_range(value: f64, units: &str, provenance: &str) -> Range {
    Range {
        nominal: value,
        min: value,
        max: value,
        units: units.into(),
        provenance: provenance.into(),
        status: "sourced".into(),
    }
}
fn unknown_range(value: f64, units: &str, provenance: &str) -> Range {
    Range {
        nominal: value,
        min: value * 0.5,
        max: value * 2.0,
        units: units.into(),
        provenance: provenance.into(),
        status: "unknown".into(),
    }
}

fn assumption_range(value: f64, units: &str, provenance: &str) -> Range {
    Range {
        nominal: value,
        min: value * 0.5,
        max: value * 2.0,
        units: units.into(),
        provenance: provenance.into(),
        status: "assembly_assumption".into(),
    }
}

/// Gaussian elimination for the small, fixed five-node thermal KCL system.
/// Pivoting is explicit so malformed conductance sets fail rather than
/// producing an apparently finite temperature from a singular matrix.
fn solve_linear_system(mut matrix: [[f64; 6]; 5]) -> Result<[f64; 5]> {
    for pivot in 0..5 {
        let mut best = pivot;
        for row in (pivot + 1)..5 {
            if matrix[row][pivot].abs() > matrix[best][pivot].abs() {
                best = row;
            }
        }
        ensure!(
            matrix[best][pivot].abs() > 1e-15,
            "thermal KCL matrix is singular"
        );
        if best != pivot {
            matrix.swap(best, pivot);
        }
        let scale = matrix[pivot][pivot];
        for value in matrix[pivot][pivot..].iter_mut() {
            *value /= scale;
        }
        let pivot_row = matrix[pivot];
        for (row_index, row_values) in matrix.iter_mut().enumerate() {
            if row_index == pivot {
                continue;
            }
            let factor = row_values[pivot];
            if factor.abs() <= 1e-15 {
                continue;
            }
            for (column, value) in row_values.iter_mut().enumerate().skip(pivot) {
                *value -= factor * pivot_row[column];
            }
        }
    }
    let mut result = [0.0; 5];
    for (index, value) in result.iter_mut().enumerate() {
        *value = matrix[index][5];
        ensure!(value.is_finite(), "thermal KCL solution is non-finite");
    }
    Ok(result)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn contract() -> PhysicalModelContract {
        let paths = NETS
            .iter()
            .enumerate()
            .map(|(i, net)| LeadPath {
                net: (*net).into(),
                pad_uuid: format!("pad-{i}"),
                trace_uuid: format!("trace-{i}"),
                trace_length_mm: sourced_range(10.0, "mm", "test"),
                trace_width_mm: sourced_range(2.0, "mm", "test"),
                copper_thickness_um: sourced_range(70.0, "um", "test"),
                lead_length_mm: sourced_range(2.0, "mm", "test"),
                lead_cross_section_mm2: sourced_range(1.0, "mm2", "test"),
                barrel_length_mm: sourced_range(1.6, "mm", "test"),
                barrel_inner_diameter_mm: sourced_range(1.6, "mm", "test"),
                barrel_plating_mm: sourced_range(0.02, "mm", "test"),
                solder_thickness_mm: sourced_range(0.2, "mm", "test"),
                solder_area_mm2: sourced_range(6.0, "mm2", "test"),
            })
            .collect();
        PhysicalModelContract {
            schema: CONTRACT_SCHEMA.into(),
            board_sha256: "a".repeat(64),
            geometry_sha256: None,
            bridge_mpn: BRIDGE_MPN.into(),
            bridge_loss_allowance_w: sourced_range(40.0, "W", "test"),
            ambient_c: 40.0,
            sink_c: 60.0,
            board_c: 80.0,
            copper_conductivity_s_m: sourced_range(5.5e7, "S/m", "test"),
            solder_conductivity_s_m: sourced_range(5e6, "S/m", "test"),
            package_to_sink_w_per_k: sourced_range(1.0, "W/K", "test"),
            lead_to_package_w_per_k: sourced_range(0.2, "W/K", "test"),
            lead_to_board_w_per_k: sourced_range(0.02, "W/K", "test"),
            junction_limit_c: 125.0,
            pcb_limit_c: 110.0,
            loss: LossInput {
                bridge_mpn: BRIDGE_MPN.into(),
                source_url: "test".into(),
                source_sha256: Some("b".repeat(64)),
                source_status: "cached_primary_text".into(),
                forward_voltage_v_at_12_5a: sourced_range(1.0, "V", "test"),
                vf_reference_current_a: 12.5,
                dynamic_resistance_ohm: None,
                conducting_diode_count: 2,
                pfc_profile_sha256: None,
            },
            paths,
        }
    }

    #[test]
    fn native_contract_binds_reviewed_stackup_dimensions() {
        let native =
            include_bytes!("../../../thermal/evidence/bridge-necks-2026-09-14/native.json");
        let manufacturing =
            include_bytes!("../../../thermal/evidence/bridge-necks-2026-09-14/manufacturing.json");
        let contract = contract_from_native(native, manufacturing).unwrap();
        assert_eq!(
            contract.board_sha256,
            "84f4b325b25e4be71fcf990d9420ddb4346687ca1c28be63fb44a0d661fa2317"
        );
        assert!(contract.geometry_sha256.is_some());
        assert_eq!(
            contract.bridge_loss_allowance_w.status,
            "assembly_assumption"
        );
        assert!(contract.paths.iter().all(|path| {
            path.copper_thickness_um.nominal == 70.0
                && path.barrel_length_mm.nominal == 1.6
                && path.copper_thickness_um.status == "sourced"
                && path.barrel_length_mm.status == "sourced"
        }));
    }

    #[test]
    fn geometry_binding_rejects_changed_drill_with_unchanged_geometry_fingerprint() {
        let native =
            include_bytes!("../../../thermal/evidence/bridge-necks-2026-09-14/native.json");
        let manufacturing =
            include_bytes!("../../../thermal/evidence/bridge-necks-2026-09-14/manufacturing.json");
        let model = crate::neck_geometry::build_neck_model_variant(native, manufacturing).unwrap();
        let mut contract = contract_from_native(native, manufacturing).unwrap();
        let fingerprint = contract.geometry_sha256.clone();
        validate_geometry_binding(&contract, &model).unwrap();

        // Keep the contract internally ordered and leave its geometry
        // fingerprint untouched.  The binding must still compare the
        // retained bore against the fresh native drill dimension.
        let bore = &mut contract.paths[0].barrel_inner_diameter_mm;
        for value in [&mut bore.nominal, &mut bore.min, &mut bore.max] {
            *value += 0.1;
        }
        assert_eq!(contract.geometry_sha256, fingerprint);
        assert!(validate_geometry_binding(&contract, &model).is_err());
    }

    #[test]
    fn reviewed_compressed_pdf_is_valid_without_plaintext_number_markers() {
        let bytes = include_bytes!("../../../thermal/cooling-options/sources/yangjie-gbu2510a.pdf");
        let mut c = contract();
        c.loss.source_status = "byte_archived".into();
        c.loss.source_sha256 = Some(REVIEWED_SOURCE_SHA256.into());
        assert!(
            evaluate_with_source_bytes(&c, &waveform(), bytes)
                .unwrap()
                .source_bytes_verified
        );
    }

    fn waveform() -> WaveformInput {
        WaveformInput {
            profile_sha256: "c".repeat(64),
            samples: vec![
                WaveformSample {
                    weight: 0.5,
                    line_sign: 1.0,
                    inductor_a: 10.0,
                },
                WaveformSample {
                    weight: 0.5,
                    line_sign: -1.0,
                    inductor_a: 10.0,
                },
            ],
            neck_rms_a: NETS.iter().map(|n| ((*n).into(), 10.0)).collect(),
        }
    }

    #[test]
    fn shared_package_heat_is_injected_once_and_balances_globally() {
        let c = contract();
        let a = evaluate(&c, &waveform()).unwrap();
        assert!(a.numerical_valid);
        assert!((a.package_heat_w - 40.0).abs() < 1e-12);
        assert!(a.total_conductor_heat_w > 0.0);
        assert!(!a.source_bytes_verified);
        assert!(a.global_power_residual_w.abs() < 1e-8);
        assert_eq!(a.necks.len(), 4);
        assert!(a.package_to_sink_w > 0.0);
        assert!(a.leads_to_board_w > 0.0);
        assert!(
            (a.package_to_leads_w - a.leads_to_board_w + a.total_conductor_heat_w).abs() < 1e-8
        );
    }

    #[test]
    fn coupled_solution_matches_independent_asymmetric_closed_form_reference() {
        let mut c = contract();
        let mut w = waveform();
        c.bridge_loss_allowance_w = sourced_range(40.0, "W", "test");
        let currents = [10.0, 12.0, 15.0, 18.0];
        for (index, net) in NETS.into_iter().enumerate() {
            // Different widths and currents make each lead heat differently;
            // the scalar reference below is reduced independently from the
            // five-node equations used by evaluate().
            c.paths[index].trace_width_mm = sourced_range(1.5 + index as f64 * 0.5, "mm", "test");
            w.neck_rms_a.insert(net.into(), currents[index]);
        }
        let g_sink = c.package_to_sink_w_per_k.nominal;
        let g_package = c.lead_to_package_w_per_k.nominal;
        let g_board = c.lead_to_board_w_per_k.nominal;
        let mut q = [0.0; 4];
        for (index, path) in c.paths.iter().enumerate() {
            let resistance = path.nominal_resistance_ohm(5.5e7, 5e6).unwrap();
            q[index] = currents[index] * currents[index] * resistance;
        }
        let effective = g_package * g_board / (g_package + g_board);
        let denominator = g_sink + 4.0 * effective;
        let numerator = g_sink * c.sink_c
            + c.bridge_loss_allowance_w.nominal
            + q.iter()
                .map(|power| g_package * (g_board * c.board_c + power) / (g_package + g_board))
                .sum::<f64>();
        let expected_package = numerator / denominator;
        let a = evaluate(&c, &w).unwrap();
        assert!((a.package_temperature_c - expected_package).abs() < 1e-9);
        for (index, neck) in a.necks.iter().enumerate() {
            let expected_lead = (g_package * expected_package + g_board * c.board_c + q[index])
                / (g_package + g_board);
            assert!((neck.temperature_c - expected_lead).abs() < 1e-9);
            assert!(neck.lead_power_residual_w.abs() < 1e-9);
        }
        assert!((a.global_heat_input_w - a.global_heat_output_w).abs() < 1e-9);
    }

    #[test]
    fn board_conductance_changes_package_temperature() {
        let mut c = contract();
        let waveform = waveform();
        let hot_board = evaluate(&c, &waveform).unwrap();
        c.lead_to_board_w_per_k = sourced_range(0.2, "W/K", "test");
        let better_board_path = evaluate(&c, &waveform).unwrap();
        assert!(better_board_path.package_temperature_c < hot_board.package_temperature_c);
        assert!(better_board_path.leads_to_board_w > hot_board.leads_to_board_w);
    }

    #[test]
    fn dynamic_forward_slope_is_applied_about_the_datasheet_reference_point() {
        let mut c = contract();
        c.loss.dynamic_resistance_ohm = Some(sourced_range(0.1, "ohm", "test"));
        let mut w = waveform();
        w.samples = vec![
            WaveformSample {
                weight: 0.5,
                line_sign: 1.0,
                inductor_a: 10.0,
            },
            WaveformSample {
                weight: 0.5,
                line_sign: -1.0,
                inductor_a: 15.0,
            },
        ];
        let a = evaluate(&c, &w).unwrap();
        // E[I]=12.5, E[I²]=162.5, so each diode is 12.5 +
        // 0.1*(162.5 - 12.5*12.5) = 13.125 W.
        assert!((a.diode_loss_w - 26.25).abs() < 1e-10);
    }

    #[test]
    fn archived_source_identity_is_checked_against_bytes() {
        let mut c = contract();
        let source = b"GBU2510A VF 12.5 A archived source";
        c.loss.source_sha256 = Some(format!("{:x}", Sha256::digest(source)));
        assert!(c.loss.validate_source_bytes(source).is_err());
        assert!(c.loss.validate_source_bytes(b"edited source").is_err());
        c.loss.source_sha256 = None;
        c.loss.source_status = "byte_archived".into();
        assert!(c.validate(&c.board_sha256).is_err());
    }

    #[test]
    fn source_bound_evaluation_does_not_promote_unreviewed_digest() {
        let mut c = contract();
        let source = b"GBU2510A VF 12.5 A archived source";
        c.loss.source_sha256 = Some(format!("{:x}", Sha256::digest(source)));
        assert!(evaluate_with_source_bytes(&c, &waveform(), source).is_err());
    }

    #[test]
    fn changing_one_path_does_not_replicate_package_source() {
        let mut c = contract();
        let mut w = waveform();
        w.neck_rms_a.insert("minus".into(), 20.0);
        let a = evaluate(&c, &w).unwrap();
        assert!((a.package_heat_w - 40.0).abs() < 1e-12);
        c.paths[0].trace_width_mm.nominal = 1.0;
        c.paths[0].trace_width_mm.min = 1.0;
        c.paths[0].trace_width_mm.max = 2.0;
        let b = evaluate(&c, &w).unwrap();
        assert!(b.total_conductor_heat_w > a.total_conductor_heat_w);
        assert!((b.package_heat_w - a.package_heat_w).abs() < 1e-12);
    }

    #[test]
    fn unknown_package_paths_keep_applicability_indeterminate() {
        let mut c = contract();
        c.paths[0].lead_length_mm.status = "unknown".into();
        let a = evaluate(&c, &waveform()).unwrap();
        assert_eq!(a.applicability, "indeterminate");
    }

    #[test]
    fn missing_neck_or_invalid_bore_fails_closed() {
        let mut c = contract();
        c.paths.pop();
        assert!(evaluate(&c, &waveform()).is_err());
        let mut c = contract();
        c.paths[0].barrel_plating_mm.nominal = c.paths[0].barrel_inner_diameter_mm.nominal;
        assert!(evaluate(&c, &waveform()).is_err());
        let mut c = contract();
        c.paths[0].trace_width_mm.units = "inches".into();
        assert!(evaluate(&c, &waveform()).is_err());
        let mut c = contract();
        c.loss.source_sha256 = Some("not-a-hash".into());
        assert!(evaluate(&c, &waveform()).is_err());
    }

    #[test]
    fn bound_waveform_hash_rejects_changed_current_or_diode_curve() {
        let mut c = contract();
        let w = waveform();
        c.loss.pfc_profile_sha256 = Some(waveform_sha256(&w).unwrap());
        assert!(evaluate(&c, &w).is_ok());
        let mut changed = w.clone();
        changed.samples[0].inductor_a = 11.0;
        assert!(evaluate(&c, &changed).is_err());
        let assessment = evaluate(&c, &w).unwrap();
        let assessment_bytes = serde_json::to_vec(&assessment).unwrap();
        let contract_bytes = serde_json::to_vec(&c).unwrap();
        assert!(replay(&contract_bytes, &assessment_bytes, &c.board_sha256, &w).is_ok());
        let mut changed_contract = c;
        changed_contract.loss.forward_voltage_v_at_12_5a.nominal = 0.9;
        let changed_bytes = serde_json::to_vec(&changed_contract).unwrap();
        assert!(replay(
            &changed_bytes,
            &assessment_bytes,
            &changed_contract.board_sha256,
            &w
        )
        .is_err());
    }

    #[test]
    fn retained_baseline_contract_is_parseable_and_board_bound() {
        let bytes = include_bytes!("../../../thermal/physical-model/contract.json");
        let c: PhysicalModelContract = serde_json::from_slice(bytes).unwrap();
        c.validate("84f4b325b25e4be71fcf990d9420ddb4346687ca1c28be63fb44a0d661fa2317")
            .unwrap();
        assert_eq!(c.paths.len(), 4);
        assert!(c.loss.source_sha256.is_none());
    }
}
