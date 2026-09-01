//! Pareto verdict for bounded regional PCB re-layout experiments.
//!
//! Measurement stays with the owning instruments (KiCad DRC, the exact
//! cross-domain pair oracle, and the Rust board parser).  This module owns the
//! acceptance contract: a creepage improvement can never buy a regression in
//! another safety category.

use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet};

pub const CORRIDOR_REQUEST_SCHEMA: &str = "temper-regional-corridor-request/v2";
pub const CORRIDOR_DECLARATION_SCHEMA: &str = "temper-regional-corridor-declaration/v2";
pub const CORRIDOR_SCREEN_SCHEMA: &str = "temper-regional-screen-request/v2";
pub const CORRIDOR_VALIDATED_SCREEN_SCHEMA: &str = "temper-regional-validated-screen-request/v4";
pub const CORRIDOR_SCREEN_VERDICT_SCHEMA: &str = "temper-regional-screen-verdict/v2";
pub const CORRIDOR_VALIDATED_SCREEN_VERDICT_SCHEMA: &str =
    "temper-regional-validated-screen-verdict/v4";

#[derive(Debug, Clone, PartialEq, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct TopologyAuthority {
    pub digest: String,
    pub clearance_key: String,
    pub clearance_mm: f64,
    pub clearance_role: temper_design_bundle::safety_value_authority::AuthorityRole,
    pub clearance_source: String,
    pub creepage_key: String,
    pub creepage_mm: f64,
    pub creepage_role: temper_design_bundle::safety_value_authority::AuthorityRole,
    pub creepage_source: String,
}

pub fn topology_authority() -> Result<TopologyAuthority, String> {
    let contract = temper_design_bundle::safety_value_authority::authority_contract()?;
    let row = |key: &str| {
        contract
            .rows
            .iter()
            .find(|row| row.key == key)
            .ok_or_else(|| format!("isolation authority is missing {key}"))
    };
    let clearance = row("clearance.hv_lv.project.target")?;
    let creepage = row("creepage.hv_lv.pd3.production")?;
    Ok(TopologyAuthority {
        digest: contract.topology_authority_digest,
        clearance_key: clearance.key.into(),
        clearance_mm: clearance.value_mm,
        clearance_role: clearance.role,
        clearance_source: clearance.source.into(),
        creepage_key: creepage.key.into(),
        creepage_mm: creepage.value_mm,
        creepage_role: creepage.role,
        creepage_source: creepage.source.into(),
    })
}

#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct CorridorDeclarationRequest {
    pub schema_version: String,
    pub declaration_hash: String,
    pub board_hash: String,
    pub generated_input_hashes: Vec<String>,
    pub placements: Vec<CorridorPlacement>,
    pub endpoint_x_mm: Vec<f64>,
    pub corridor_x_mm: Vec<f64>,
    pub entry_y_mm: Vec<f64>,
    pub endpoint_y_mm: f64,
    pub fixed_start: [f64; 2],
    pub knee_y_mm: f64,
    pub layer: String,
    pub route_width_mm: f64,
    pub via_diameter_mm: f64,
    pub via_drill_mm: f64,
    pub via_span: [String; 2],
    pub candidate_budget: usize,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct CorridorPlacement {
    pub placement_id: String,
    pub j1_position: [f64; 2],
}

#[derive(Debug, Clone, PartialEq, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct CorridorCandidateIdentity {
    pub ordinal: usize,
    pub candidate_id: String,
    pub placement_id: String,
    pub j1_position: [f64; 2],
    pub endpoint_x_mm: f64,
    pub corridor_x_mm: f64,
    pub entry_y_mm: f64,
    pub route_points: Vec<[f64; 2]>,
}

#[derive(Debug, Clone, PartialEq, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct CorridorDeclaration {
    pub schema_version: String,
    pub declaration_hash: String,
    pub board_hash: String,
    pub generated_input_hashes: Vec<String>,
    pub topology_authority: TopologyAuthority,
    pub candidate_count: usize,
    pub candidate_set_digest: String,
    pub candidates: Vec<CorridorCandidateIdentity>,
}

fn validate_digest(label: &str, digest: &str) -> Result<(), String> {
    if digest.len() != 64 || !digest.bytes().all(|byte| byte.is_ascii_hexdigit()) {
        return Err(format!("{label} must be a 64-character hexadecimal digest"));
    }
    Ok(())
}

fn finite_positive(label: &str, values: &[f64]) -> Result<(), String> {
    if values.is_empty()
        || values
            .iter()
            .any(|value| !value.is_finite() || *value <= 0.0)
    {
        return Err(format!("{label} must be non-empty, finite, and positive"));
    }
    Ok(())
}

pub fn declare_corridor_candidates(
    mut request: CorridorDeclarationRequest,
) -> Result<CorridorDeclaration, String> {
    if request.schema_version != CORRIDOR_REQUEST_SCHEMA {
        return Err(format!(
            "unsupported corridor request schema {}",
            request.schema_version
        ));
    }
    validate_digest("declaration_hash", &request.declaration_hash)?;
    validate_digest("board_hash", &request.board_hash)?;
    if request.generated_input_hashes.is_empty() {
        return Err("at least one generated-input hash is required".into());
    }
    for digest in &request.generated_input_hashes {
        validate_digest("generated_input_hash", digest)?;
    }
    request.generated_input_hashes.sort();
    if request
        .generated_input_hashes
        .windows(2)
        .any(|window| window[0] == window[1])
    {
        return Err("generated-input hashes must be unique".into());
    }
    if request.placements.is_empty()
        || request.placements.iter().any(|row| {
            row.placement_id.trim().is_empty()
                || row.j1_position.iter().any(|value| !value.is_finite())
        })
    {
        return Err("placement identities and J1 positions must be non-empty".into());
    }
    finite_positive("endpoint_x_mm", &request.endpoint_x_mm)?;
    finite_positive("corridor_x_mm", &request.corridor_x_mm)?;
    finite_positive("entry_y_mm", &request.entry_y_mm)?;
    finite_positive(
        "route geometry",
        &[
            request.endpoint_y_mm,
            request.fixed_start[0],
            request.fixed_start[1],
            request.knee_y_mm,
            request.route_width_mm,
            request.via_diameter_mm,
            request.via_drill_mm,
        ],
    )?;
    if request.layer != "In3.Cu" || request.via_span != ["In3.Cu", "F.Cu"] {
        return Err("corridor v2 permits only In3.Cu with an In3.Cu-to-F.Cu blind via".into());
    }
    request
        .placements
        .sort_by(|a, b| a.placement_id.cmp(&b.placement_id));
    request.endpoint_x_mm.sort_by(f64::total_cmp);
    request.corridor_x_mm.sort_by(f64::total_cmp);
    request.entry_y_mm.sort_by(f64::total_cmp);
    let unique = |values: &[f64]| !values.windows(2).any(|window| window[0] == window[1]);
    if request
        .placements
        .windows(2)
        .any(|window| window[0].placement_id == window[1].placement_id)
        || !unique(&request.endpoint_x_mm)
        || !unique(&request.corridor_x_mm)
        || !unique(&request.entry_y_mm)
    {
        return Err("corridor declaration axes must be unique".into());
    }
    let cardinality = [
        request.placements.len(),
        request.endpoint_x_mm.len(),
        request.corridor_x_mm.len(),
        request.entry_y_mm.len(),
    ]
    .into_iter()
    .try_fold(1usize, |total, count| total.checked_mul(count))
    .ok_or_else(|| "candidate cardinality overflow".to_string())?;
    if cardinality != request.candidate_budget {
        return Err(format!(
            "declared cardinality {cardinality} does not equal candidate budget {}",
            request.candidate_budget
        ));
    }
    let authority = topology_authority()?;
    let mut candidates = Vec::with_capacity(cardinality);
    for placement in &request.placements {
        for endpoint_x_mm in &request.endpoint_x_mm {
            for corridor_x_mm in &request.corridor_x_mm {
                for entry_y_mm in &request.entry_y_mm {
                    let route_points = vec![
                        request.fixed_start,
                        [*corridor_x_mm, *entry_y_mm],
                        [*corridor_x_mm, request.knee_y_mm],
                        [*endpoint_x_mm, request.endpoint_y_mm],
                    ];
                    let identity = (
                        &request.declaration_hash,
                        &request.board_hash,
                        &request.generated_input_hashes,
                        &authority.digest,
                        &placement.placement_id,
                        &placement.j1_position,
                        endpoint_x_mm,
                        corridor_x_mm,
                        entry_y_mm,
                        &route_points,
                        &request.layer,
                        request.route_width_mm,
                        request.via_diameter_mm,
                        request.via_drill_mm,
                        &request.via_span,
                    );
                    let digest =
                        temper_design_bundle::regional_topology::candidate_digest(&identity)?;
                    let candidate_id = format!("NET41-CORRIDOR-{digest}");
                    candidates.push(CorridorCandidateIdentity {
                        ordinal: candidates.len() + 1,
                        candidate_id,
                        placement_id: placement.placement_id.clone(),
                        j1_position: placement.j1_position,
                        endpoint_x_mm: *endpoint_x_mm,
                        corridor_x_mm: *corridor_x_mm,
                        entry_y_mm: *entry_y_mm,
                        route_points,
                    });
                }
            }
        }
    }
    if candidates
        .iter()
        .map(|row| &row.candidate_id)
        .collect::<BTreeSet<_>>()
        .len()
        != candidates.len()
    {
        return Err("corridor candidate digest collision".into());
    }
    let mut declaration = CorridorDeclaration {
        schema_version: CORRIDOR_DECLARATION_SCHEMA.to_string(),
        declaration_hash: request.declaration_hash,
        board_hash: request.board_hash,
        generated_input_hashes: request.generated_input_hashes,
        topology_authority: authority,
        candidate_count: candidates.len(),
        candidate_set_digest: String::new(),
        candidates,
    };
    declaration.candidate_set_digest = corridor_declaration_digest(&declaration)?;
    Ok(declaration)
}

fn corridor_declaration_digest(declaration: &CorridorDeclaration) -> Result<String, String> {
    let mut envelope = serde_json::to_value(declaration)
        .map_err(|error| format!("failed to serialize corridor declaration: {error}"))?;
    envelope
        .as_object_mut()
        .ok_or_else(|| "corridor declaration must serialize as an object".to_string())?
        .remove("candidate_set_digest");
    temper_design_bundle::regional_topology::candidate_digest(&envelope)
}

/// Derive the immutable corridor family from its bound declaration and
/// predecessor manifest.  Callers transport evidence bytes; Rust owns the
/// selector, placement identities, and request construction.
pub fn declare_corridor_candidates_from_evidence(
    declaration_json: &str,
    predecessor_manifest_json: &str,
) -> Result<CorridorDeclaration, String> {
    let declaration: serde_json::Value = serde_json::from_str(declaration_json)
        .map_err(|error| format!("invalid declaration JSON: {error}"))?;
    let predecessor: serde_json::Value = serde_json::from_str(predecessor_manifest_json)
        .map_err(|error| format!("invalid predecessor manifest JSON: {error}"))?;
    let family = declaration
        .get("family")
        .and_then(serde_json::Value::as_object)
        .ok_or_else(|| "declaration has no family object".to_string())?;
    if family
        .get("placement_selector")
        .and_then(serde_json::Value::as_str)
        != Some("one row per predecessor_placement_id at east_shift_mm == 4.0")
    {
        return Err("unsupported predecessor placement selector".into());
    }
    let rows = predecessor
        .pointer("/results")
        .and_then(serde_json::Value::as_array)
        .ok_or_else(|| "predecessor manifest has no results".to_string())?;
    let mut placements = Vec::new();
    for row in rows {
        if row
            .pointer("/east_shift_mm")
            .and_then(serde_json::Value::as_f64)
            != Some(4.0)
        {
            continue;
        }
        let placement_id = row
            .pointer("/predecessor_placement_id")
            .and_then(serde_json::Value::as_str)
            .ok_or_else(|| "selected predecessor row has no placement id".to_string())?;
        let j1 = row
            .pointer("/placements/J1")
            .and_then(serde_json::Value::as_array)
            .ok_or_else(|| format!("selected predecessor {placement_id} has no J1 placement"))?;
        if j1.len() < 2 {
            return Err(format!(
                "selected predecessor {placement_id} has an incomplete J1 placement"
            ));
        }
        let coordinate = |index: usize| {
            j1[index].as_f64().ok_or_else(|| {
                format!("selected predecessor {placement_id} has invalid J1 geometry")
            })
        };
        placements.push(CorridorPlacement {
            placement_id: placement_id.to_string(),
            j1_position: [coordinate(0)?, coordinate(1)?],
        });
    }
    let generated_input_hashes = declaration
        .pointer("/generated_inputs")
        .and_then(serde_json::Value::as_object)
        .ok_or_else(|| "declaration has no generated-input identities".to_string())?
        .values()
        .map(|value| {
            value
                .as_str()
                .map(str::to_string)
                .ok_or_else(|| "generated-input identity must be a string".to_string())
        })
        .collect::<Result<Vec<_>, _>>()?;
    let field = |name: &str| {
        family
            .get(name)
            .cloned()
            .ok_or_else(|| format!("declaration family is missing {name}"))
    };
    let request: CorridorDeclarationRequest = serde_json::from_value(serde_json::json!({
        "schema_version": field("schema_version")?,
        "declaration_hash": declaration.pointer("/declaration_authority_digest").cloned()
            .ok_or_else(|| "declaration has no authority digest".to_string())?,
        "board_hash": declaration.pointer("/production_board_sha256").cloned()
            .ok_or_else(|| "declaration has no production-board digest".to_string())?,
        "generated_input_hashes": generated_input_hashes,
        "placements": placements,
        "endpoint_x_mm": field("endpoint_x_mm")?,
        "corridor_x_mm": field("corridor_x_mm")?,
        "entry_y_mm": field("entry_y_mm")?,
        "endpoint_y_mm": field("endpoint_y_mm")?,
        "fixed_start": field("fixed_start")?,
        "knee_y_mm": field("knee_y_mm")?,
        "layer": field("layer")?,
        "route_width_mm": field("route_width_mm")?,
        "via_diameter_mm": field("via_diameter_mm")?,
        "via_drill_mm": field("via_drill_mm")?,
        "via_span": field("via_span")?,
        "candidate_budget": field("candidate_budget")?,
    }))
    .map_err(|error| format!("invalid bound corridor family: {error}"))?;
    declare_corridor_candidates(request)
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct RawCorridorMeasurements {
    pub candidate_id: String,
    pub minimum_clearance_mm: f64,
    /// Euclidean copper distance is a conservative lower bound on the path
    /// length creepage instrument. It may prove a pass, never manufacture one.
    pub minimum_creepage_lower_bound_mm: f64,
    pub route_length_mm: f64,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct CorridorScreenRequest {
    pub schema_version: String,
    pub candidates: Vec<RawCorridorMeasurements>,
    pub route_budget: usize,
}

#[derive(Debug, Serialize)]
pub struct AttributedVeto {
    pub authority_key: String,
    pub required_mm: f64,
    pub authority_role: temper_design_bundle::safety_value_authority::AuthorityRole,
    pub measured_mm: f64,
    pub source: String,
}

#[derive(Debug, Serialize)]
pub struct CorridorScreenResult {
    pub candidate_id: String,
    pub raw_measurements: RawCorridorMeasurements,
    pub vetoes: Vec<AttributedVeto>,
}

#[derive(Debug, Serialize)]
pub struct CorridorScreenVerdict {
    pub schema_version: &'static str,
    pub topology_authority: TopologyAuthority,
    pub results: Vec<CorridorScreenResult>,
    pub clearance_creepage_prefilter_subset: Vec<String>,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct CorridorValidatedScreenRequest {
    pub schema_version: String,
    pub candidates: Vec<RawCorridorMeasurements>,
    pub route_budget: usize,
}

pub struct CorridorEvidenceInputs<'a> {
    pub declaration_json: &'a str,
    pub basis_json: &'a str,
    pub board_text: &'a str,
    pub predecessor_receipt_json: &'a str,
    pub predecessor_manifest_json: &'a str,
    pub domain_manifest_text: &'a str,
    pub netlist_text: &'a str,
    pub kicad_dru_text: &'a str,
}

#[derive(Debug, Serialize)]
pub struct CorridorValidatedScreenVerdict {
    pub schema_version: &'static str,
    pub declaration_hash: String,
    pub candidate_set_digest: String,
    pub evaluated_count: usize,
    pub topology_authority: TopologyAuthority,
    pub results: Vec<CorridorScreenResult>,
    pub clearance_creepage_prefilter_subset: Vec<String>,
}

pub fn screen_corridor_candidates(
    request: CorridorScreenRequest,
) -> Result<CorridorScreenVerdict, String> {
    if request.schema_version != CORRIDOR_SCREEN_SCHEMA
        || request.route_budget == 0
        || request.candidates.is_empty()
    {
        return Err("invalid corridor screening request".into());
    }
    let authority = topology_authority()?;
    let mut seen = BTreeSet::new();
    let mut results = Vec::with_capacity(request.candidates.len());
    for raw in request.candidates {
        if raw.candidate_id.trim().is_empty()
            || !seen.insert(raw.candidate_id.clone())
            || !raw.minimum_clearance_mm.is_finite()
            || !raw.minimum_creepage_lower_bound_mm.is_finite()
            || !raw.route_length_mm.is_finite()
            || raw.route_length_mm < 0.0
        {
            return Err(
                "candidate identities and measurements must be unique, finite, and valid".into(),
            );
        }
        let mut vetoes = Vec::new();
        if raw.minimum_clearance_mm < authority.clearance_mm {
            vetoes.push(AttributedVeto {
                authority_key: authority.clearance_key.clone(),
                required_mm: authority.clearance_mm,
                authority_role: authority.clearance_role,
                measured_mm: raw.minimum_clearance_mm,
                source: authority.clearance_source.clone(),
            });
        }
        if raw.minimum_creepage_lower_bound_mm < authority.creepage_mm {
            vetoes.push(AttributedVeto {
                authority_key: authority.creepage_key.clone(),
                required_mm: authority.creepage_mm,
                authority_role: authority.creepage_role,
                measured_mm: raw.minimum_creepage_lower_bound_mm,
                source: authority.creepage_source.clone(),
            });
        }
        results.push(CorridorScreenResult {
            candidate_id: raw.candidate_id.clone(),
            raw_measurements: raw,
            vetoes,
        });
    }
    let mut survivors: Vec<_> = results.iter().filter(|row| row.vetoes.is_empty()).collect();
    survivors.sort_by(|a, b| {
        let a_margin = (a.raw_measurements.minimum_clearance_mm - authority.clearance_mm)
            .min(a.raw_measurements.minimum_creepage_lower_bound_mm - authority.creepage_mm);
        let b_margin = (b.raw_measurements.minimum_clearance_mm - authority.clearance_mm)
            .min(b.raw_measurements.minimum_creepage_lower_bound_mm - authority.creepage_mm);
        b_margin
            .total_cmp(&a_margin)
            .then(
                b.raw_measurements
                    .minimum_clearance_mm
                    .total_cmp(&a.raw_measurements.minimum_clearance_mm),
            )
            .then(
                b.raw_measurements
                    .minimum_creepage_lower_bound_mm
                    .total_cmp(&a.raw_measurements.minimum_creepage_lower_bound_mm),
            )
            .then(
                a.raw_measurements
                    .route_length_mm
                    .total_cmp(&b.raw_measurements.route_length_mm),
            )
            .then(a.candidate_id.cmp(&b.candidate_id))
    });
    let clearance_creepage_prefilter_subset = survivors
        .into_iter()
        .map(|row| row.candidate_id.clone())
        .collect();
    results.sort_by(|a, b| a.candidate_id.cmp(&b.candidate_id));
    Ok(CorridorScreenVerdict {
        schema_version: CORRIDOR_SCREEN_VERDICT_SCHEMA,
        topology_authority: authority,
        results,
        clearance_creepage_prefilter_subset,
    })
}

fn screen_validated_corridor_candidates(
    candidate_set: CorridorDeclaration,
    request: CorridorValidatedScreenRequest,
) -> Result<CorridorValidatedScreenVerdict, String> {
    if request.schema_version != CORRIDOR_VALIDATED_SCREEN_SCHEMA
        || candidate_set.schema_version != CORRIDOR_DECLARATION_SCHEMA
        || request.route_budget == 0
        || request.route_budget > candidate_set.candidate_count
    {
        return Err("invalid validated corridor screening request".into());
    }
    let live_authority = topology_authority()?;
    if candidate_set.topology_authority != live_authority
        || candidate_set.candidate_count != candidate_set.candidates.len()
        || candidate_set.candidate_set_digest != corridor_declaration_digest(&candidate_set)?
    {
        return Err("candidate set is stale, incomplete, or authority-mismatched".into());
    }
    let expected_ids: BTreeSet<_> = request
        .candidates
        .iter()
        .map(|candidate| candidate.candidate_id.as_str())
        .collect();
    let declared_ids: BTreeSet<_> = candidate_set
        .candidates
        .iter()
        .map(|candidate| candidate.candidate_id.as_str())
        .collect();
    if declared_ids.len() != candidate_set.candidates.len()
        || expected_ids.len() != request.candidates.len()
        || expected_ids != declared_ids
    {
        return Err("screening measurements do not cover the exact declared candidate set".into());
    }
    let declaration_hash = candidate_set.declaration_hash.clone();
    let candidate_set_digest = candidate_set.candidate_set_digest.clone();
    let evaluated_count = request.candidates.len();
    let verdict = screen_corridor_candidates(CorridorScreenRequest {
        schema_version: CORRIDOR_SCREEN_SCHEMA.to_string(),
        candidates: request.candidates,
        route_budget: request.route_budget,
    })?;
    Ok(CorridorValidatedScreenVerdict {
        schema_version: CORRIDOR_VALIDATED_SCREEN_VERDICT_SCHEMA,
        declaration_hash,
        candidate_set_digest,
        evaluated_count,
        topology_authority: verdict.topology_authority,
        results: verdict.results,
        clearance_creepage_prefilter_subset: verdict.clearance_creepage_prefilter_subset,
    })
}

/// Validate the complete evidence envelope and screen its Rust-derived family
/// in one transaction.  No receipt or candidate declaration crosses the
/// caller boundary, so neither authority can be forged or substituted.
pub fn validate_corridor_evidence(
    evidence: &CorridorEvidenceInputs<'_>,
) -> Result<CorridorDeclaration, String> {
    let candidate_set = declare_corridor_candidates_from_evidence(
        evidence.declaration_json,
        evidence.predecessor_manifest_json,
    )?;
    let candidate_set_json = serde_json::to_string(&candidate_set)
        .map_err(|error| format!("candidate-set serialization failed: {error}"))?;
    temper_design_bundle::regional_topology::validate_declaration(
        &temper_design_bundle::regional_topology::DeclarationInputs {
            declaration_json: evidence.declaration_json,
            basis_json: evidence.basis_json,
            board_text: evidence.board_text,
            predecessor_receipt_json: evidence.predecessor_receipt_json,
            predecessor_manifest_json: evidence.predecessor_manifest_json,
            domain_manifest_text: evidence.domain_manifest_text,
            netlist_text: evidence.netlist_text,
            kicad_dru_text: evidence.kicad_dru_text,
            candidate_set_json: &candidate_set_json,
        },
    )?;
    Ok(candidate_set)
}

pub fn validate_and_screen_corridor_evidence(
    evidence: &CorridorEvidenceInputs<'_>,
    request: CorridorValidatedScreenRequest,
) -> Result<CorridorValidatedScreenVerdict, String> {
    let candidate_set = validate_corridor_evidence(evidence)?;
    screen_validated_corridor_candidates(candidate_set, request)
}

const HARD_VETO_DRC_RULES: &[&str] = &[
    "shorting_items",
    "clearance",
    "hole_clearance",
    "copper_edge_clearance",
];

#[derive(Debug, Clone, PartialEq)]
pub struct RegionalCandidateIdentity {
    pub ordinal: usize,
    pub candidate_id: String,
    pub placement_id: String,
    pub east_shift_mm: f64,
}

#[derive(Debug, Clone, PartialEq)]
pub struct PreRouteCandidateInput {
    pub k1_j1_gap_mm: f64,
    pub route_to_selv_gap_mm: f64,
    pub affected_safety_count: usize,
    pub new_safety_count: usize,
    pub worsened_safety_count: usize,
    pub new_body_overlap_count: usize,
    pub worsened_body_overlap_count: usize,
    pub new_courtyard_overlap_count: usize,
    pub worsened_courtyard_overlap_count: usize,
    pub containment_failure_count: usize,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PreRouteCandidateVerdict {
    pub accepted: bool,
    pub reasons: Vec<String>,
}

/// Apply the first-family pre-route vetoes in one canonical order.
pub fn evaluate_pre_route_candidate(input: &PreRouteCandidateInput) -> PreRouteCandidateVerdict {
    let mut reasons = Vec::new();
    let required_creepage_mm = match topology_authority() {
        Ok(authority) => authority.creepage_mm,
        Err(error) => {
            reasons.push(format!("topology_authority:{error}"));
            f64::INFINITY
        }
    };
    if input.k1_j1_gap_mm < required_creepage_mm + 0.5 {
        reasons.push("k1_j1".to_string());
    }
    if input.route_to_selv_gap_mm < required_creepage_mm {
        reasons.push("route_to_selv".to_string());
    }
    if input.affected_safety_count > 0 {
        reasons.push("affected_safety".to_string());
    }
    if input.new_safety_count > 0 || input.worsened_safety_count > 0 {
        reasons.push("safety_regression".to_string());
    }
    if input.new_body_overlap_count > 0 || input.worsened_body_overlap_count > 0 {
        reasons.push("body_overlap".to_string());
    }
    if input.new_courtyard_overlap_count > 0 || input.worsened_courtyard_overlap_count > 0 {
        reasons.push("courtyard_overlap".to_string());
    }
    if input.containment_failure_count > 0 {
        reasons.push("containment".to_string());
    }
    PreRouteCandidateVerdict {
        accepted: reasons.is_empty(),
        reasons,
    }
}

/// Declare a finite first-family Cartesian product in a stable order.
///
/// The returned ordinal is the campaign identity. Board content hashes are
/// recorded after materialization; this function deliberately does not
/// pretend that an ordinal is a content digest.
pub fn declare_regional_candidates(
    mut placement_ids: Vec<String>,
    mut east_shifts_mm: Vec<f64>,
    placement_budget: usize,
) -> Result<Vec<RegionalCandidateIdentity>, String> {
    if placement_ids.is_empty() {
        return Err("at least one predecessor placement is required".into());
    }
    if east_shifts_mm.is_empty() {
        return Err("at least one east-shift template is required".into());
    }
    if placement_budget == 0 {
        return Err("placement budget must be positive".into());
    }
    if placement_ids.iter().any(|id| id.trim().is_empty()) {
        return Err("placement ids must be non-empty".into());
    }
    if east_shifts_mm.iter().any(|v| !v.is_finite() || *v <= 0.0) {
        return Err("east shifts must be finite and positive".into());
    }

    placement_ids.sort();
    east_shifts_mm.sort_by(f64::total_cmp);
    if placement_ids.windows(2).any(|w| w[0] == w[1]) {
        return Err("placement ids must be unique".into());
    }
    if east_shifts_mm.windows(2).any(|w| w[0] == w[1]) {
        return Err("east shifts must be unique".into());
    }

    let cardinality = placement_ids
        .len()
        .checked_mul(east_shifts_mm.len())
        .ok_or_else(|| "candidate cardinality overflow".to_string())?;
    if cardinality > placement_budget {
        return Err(format!(
            "declared candidate cardinality {cardinality} exceeds placement budget {placement_budget}"
        ));
    }

    let mut rows = Vec::with_capacity(cardinality);
    for placement_id in placement_ids {
        for east_shift_mm in &east_shifts_mm {
            let ordinal = rows.len() + 1;
            rows.push(RegionalCandidateIdentity {
                ordinal,
                candidate_id: format!("R14HV-{ordinal:03}"),
                placement_id: placement_id.clone(),
                east_shift_mm: *east_shift_mm,
            });
        }
    }
    Ok(rows)
}

#[derive(Debug, Clone, PartialEq)]
pub struct RegionalSnapshot {
    pub cross_domain_pairs: BTreeSet<String>,
    pub drc_errors_by_rule: BTreeMap<String, usize>,
    pub body_overlap_by_pair: BTreeMap<String, f64>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct RegionalVerdict {
    pub accepted: bool,
    pub improved: bool,
    pub reasons: Vec<String>,
    pub new_cross_domain_pairs: Vec<String>,
    pub removed_cross_domain_pairs: Vec<String>,
    pub drc_rule_deltas: BTreeMap<String, isize>,
    pub new_or_worsened_body_pairs: Vec<String>,
    pub routed_pad_endpoint_drift: Vec<String>,
}

pub fn routed_pad_endpoint_drift(
    baseline_pads: &[(String, f64, f64)],
    baseline_endpoints: &[(f64, f64)],
    candidate_pads: &[(String, f64, f64)],
    candidate_endpoints: &[(f64, f64)],
    tolerance_mm: f64,
) -> Vec<String> {
    fn connected(
        pads: &[(String, f64, f64)],
        endpoints: &[(f64, f64)],
        tolerance_mm: f64,
    ) -> BTreeSet<String> {
        let tol2 = tolerance_mm * tolerance_mm;
        pads.iter()
            .filter(|(_, x, y)| {
                endpoints.iter().any(|(ex, ey)| {
                    let dx = x - ex;
                    let dy = y - ey;
                    dx * dx + dy * dy <= tol2
                })
            })
            .map(|(id, _, _)| id.clone())
            .collect()
    }

    let before = connected(baseline_pads, baseline_endpoints, tolerance_mm);
    let after = connected(candidate_pads, candidate_endpoints, tolerance_mm);
    before.difference(&after).cloned().collect()
}

pub fn evaluate_regional_candidate(
    baseline: &RegionalSnapshot,
    candidate: &RegionalSnapshot,
    endpoint_drift: Vec<String>,
    instrument_errors: Vec<String>,
) -> RegionalVerdict {
    let new_pairs: Vec<_> = candidate
        .cross_domain_pairs
        .difference(&baseline.cross_domain_pairs)
        .cloned()
        .collect();
    let removed_pairs: Vec<_> = baseline
        .cross_domain_pairs
        .difference(&candidate.cross_domain_pairs)
        .cloned()
        .collect();

    let rules: BTreeSet<_> = baseline
        .drc_errors_by_rule
        .keys()
        .chain(candidate.drc_errors_by_rule.keys())
        .cloned()
        .collect();
    let drc_rule_deltas: BTreeMap<_, _> = rules
        .into_iter()
        .map(|rule| {
            let before = *baseline.drc_errors_by_rule.get(&rule).unwrap_or(&0);
            let after = *candidate.drc_errors_by_rule.get(&rule).unwrap_or(&0);
            (rule, after as isize - before as isize)
        })
        .collect();

    let new_or_worsened_body_pairs: Vec<_> = candidate
        .body_overlap_by_pair
        .iter()
        .filter_map(|(pair, after)| {
            let before = baseline
                .body_overlap_by_pair
                .get(pair)
                .copied()
                .unwrap_or(0.0);
            (*after > before + 1e-6).then(|| pair.clone())
        })
        .collect();

    let baseline_total: usize = baseline.drc_errors_by_rule.values().sum();
    let candidate_total: usize = candidate.drc_errors_by_rule.values().sum();
    let mut reasons = instrument_errors;
    if !new_pairs.is_empty() {
        reasons.push(format!("{} new HV<->SELV pair(s)", new_pairs.len()));
    }
    if candidate_total > baseline_total {
        reasons.push(format!(
            "total DRC findings rose from {baseline_total} to {candidate_total}"
        ));
    }
    for rule in HARD_VETO_DRC_RULES {
        if drc_rule_deltas.get(*rule).copied().unwrap_or(0) > 0 {
            reasons.push(format!("hard-veto DRC rule {rule} increased"));
        }
    }
    if !new_or_worsened_body_pairs.is_empty() {
        reasons.push(format!(
            "{} new or worsened F.Fab body collision(s)",
            new_or_worsened_body_pairs.len()
        ));
    }
    if !endpoint_drift.is_empty() {
        reasons.push(format!(
            "{} previously routed pad endpoint(s) lost connectivity",
            endpoint_drift.len()
        ));
    }

    let body_improved = baseline.body_overlap_by_pair.iter().any(|(pair, before)| {
        candidate
            .body_overlap_by_pair
            .get(pair)
            .copied()
            .unwrap_or(0.0)
            + 1e-6
            < *before
    });
    let improved = !removed_pairs.is_empty() || candidate_total < baseline_total || body_improved;
    if !improved {
        reasons.push("candidate is non-regressing but does not improve any tracked axis".into());
    }

    RegionalVerdict {
        accepted: reasons.is_empty(),
        improved,
        reasons,
        new_cross_domain_pairs: new_pairs,
        removed_cross_domain_pairs: removed_pairs,
        drc_rule_deltas,
        new_or_worsened_body_pairs,
        routed_pad_endpoint_drift: endpoint_drift,
    }
}

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

    #[cfg_attr(test, test)]
    fn pre_route_verdict_owns_canonical_reason_order() {
        let verdict = evaluate_pre_route_candidate(&PreRouteCandidateInput {
            k1_j1_gap_mm: 12.0,
            route_to_selv_gap_mm: 11.0,
            affected_safety_count: 1,
            new_safety_count: 1,
            worsened_safety_count: 1,
            new_body_overlap_count: 1,
            worsened_body_overlap_count: 1,
            new_courtyard_overlap_count: 1,
            worsened_courtyard_overlap_count: 1,
            containment_failure_count: 1,
        });
        assert!(!verdict.accepted);
        assert_eq!(
            verdict.reasons,
            [
                "k1_j1",
                "route_to_selv",
                "affected_safety",
                "safety_regression",
                "body_overlap",
                "courtyard_overlap",
                "containment"
            ]
        );
    }

    #[cfg_attr(test, test)]
    fn pre_route_verdict_accepts_only_an_empty_veto_set() {
        let verdict = evaluate_pre_route_candidate(&PreRouteCandidateInput {
            k1_j1_gap_mm: 13.1,
            route_to_selv_gap_mm: 12.6,
            affected_safety_count: 0,
            new_safety_count: 0,
            worsened_safety_count: 0,
            new_body_overlap_count: 0,
            worsened_body_overlap_count: 0,
            new_courtyard_overlap_count: 0,
            worsened_courtyard_overlap_count: 0,
            containment_failure_count: 0,
        });
        assert!(verdict.accepted);
        assert!(verdict.reasons.is_empty());
    }

    fn snapshot(pairs: &[&str], drc: &[(&str, usize)], bodies: &[(&str, f64)]) -> RegionalSnapshot {
        RegionalSnapshot {
            cross_domain_pairs: pairs.iter().map(|s| (*s).to_string()).collect(),
            drc_errors_by_rule: drc.iter().map(|(k, v)| ((*k).to_string(), *v)).collect(),
            body_overlap_by_pair: bodies.iter().map(|(k, v)| ((*k).to_string(), *v)).collect(),
        }
    }

    #[cfg_attr(test, test)]
    fn accepts_real_pareto_improvement() {
        let before = snapshot(&["A<->B", "C<->D"], &[("creepage", 10)], &[]);
        let after = snapshot(&["C<->D"], &[("creepage", 9)], &[]);
        let verdict = evaluate_regional_candidate(&before, &after, vec![], vec![]);
        assert!(verdict.accepted);
        assert!(verdict.improved);
    }

    #[cfg_attr(test, test)]
    fn rejects_creepage_win_that_buys_a_short() {
        let before = snapshot(&["A<->B"], &[("creepage", 10), ("shorting_items", 2)], &[]);
        let after = snapshot(&[], &[("creepage", 9), ("shorting_items", 3)], &[]);
        let verdict = evaluate_regional_candidate(&before, &after, vec![], vec![]);
        assert!(!verdict.accepted);
        assert!(verdict.reasons.iter().any(|r| r.contains("shorting_items")));
    }

    #[cfg_attr(test, test)]
    fn rejects_new_pair_even_when_counts_fall() {
        let before = snapshot(&["A<->B", "C<->D"], &[("creepage", 10)], &[]);
        let after = snapshot(&["C<->D", "E<->F"], &[("creepage", 9)], &[]);
        let verdict = evaluate_regional_candidate(&before, &after, vec![], vec![]);
        assert!(!verdict.accepted);
        assert_eq!(verdict.new_cross_domain_pairs, vec!["E<->F"]);
    }

    #[cfg_attr(test, test)]
    fn rejects_body_collision_endpoint_drift_and_instrument_error() {
        let before = snapshot(&["A<->B"], &[("creepage", 10)], &[("C1<->C2", 1.0)]);
        let after = snapshot(&[], &[("creepage", 9)], &[("C1<->C2", 1.1)]);
        let verdict = evaluate_regional_candidate(
            &before,
            &after,
            vec!["U1.1".into()],
            vec!["candidate DRC hit a reporting cap".into()],
        );
        assert!(!verdict.accepted);
        assert_eq!(verdict.reasons.len(), 3);
    }

    #[cfg_attr(test, test)]
    fn endpoint_drift_tracks_pad_identity_not_coordinate() {
        let before_pads = vec![("U1.1".into(), 1.0, 1.0)];
        let after_pads = vec![("U1.1".into(), 2.0, 1.0)];
        let endpoints = vec![(1.0, 1.0)];
        assert_eq!(
            routed_pad_endpoint_drift(&before_pads, &endpoints, &after_pads, &endpoints, 0.01),
            vec!["U1.1"]
        );
    }

    #[cfg_attr(test, test)]
    fn regional_declaration_is_deterministic_and_budgeted() {
        let a = declare_regional_candidates(
            vec!["C002".into(), "C001".into()],
            vec![5.5, 4.0, 5.0, 4.5],
            8,
        )
        .expect("valid bounded family");
        let b = declare_regional_candidates(
            vec!["C001".into(), "C002".into()],
            vec![4.0, 4.5, 5.0, 5.5],
            8,
        )
        .expect("input order must not matter");
        assert_eq!(a, b);
        assert_eq!(a.len(), 8);
        assert_eq!(a[0].candidate_id, "R14HV-001");
        assert_eq!(a[0].placement_id, "C001");
        assert_eq!(a[0].east_shift_mm, 4.0);
        assert!(declare_regional_candidates(vec!["C001".into()], vec![4.0, 4.5], 1).is_err());
    }

    fn corridor_declaration() -> CorridorDeclaration {
        declare_corridor_candidates(CorridorDeclarationRequest {
            schema_version: CORRIDOR_REQUEST_SCHEMA.into(),
            declaration_hash: "d".repeat(64),
            board_hash: "b".repeat(64),
            generated_input_hashes: vec!["a".repeat(64)],
            placements: vec![
                CorridorPlacement {
                    placement_id: "P002".into(),
                    j1_position: [101.0, 200.0],
                },
                CorridorPlacement {
                    placement_id: "P001".into(),
                    j1_position: [100.0, 200.0],
                },
            ],
            endpoint_x_mm: vec![122.64],
            corridor_x_mm: vec![120.0],
            entry_y_mm: vec![226.0],
            endpoint_y_mm: 252.5225,
            fixed_start: [112.0, 206.0],
            knee_y_mm: 250.0,
            layer: "In3.Cu".into(),
            route_width_mm: 0.5,
            via_diameter_mm: 0.9,
            via_drill_mm: 0.3,
            via_span: ["In3.Cu".into(), "F.Cu".into()],
            candidate_budget: 2,
        })
        .expect("valid corridor family")
    }

    fn corridor_measurements(declaration: &CorridorDeclaration) -> Vec<RawCorridorMeasurements> {
        declaration
            .candidates
            .iter()
            .enumerate()
            .map(|(index, candidate)| RawCorridorMeasurements {
                candidate_id: candidate.candidate_id.clone(),
                minimum_clearance_mm: if index == 0 { 6.0 } else { 5.9 },
                minimum_creepage_lower_bound_mm: 12.6,
                route_length_mm: 10.0,
            })
            .collect()
    }

    #[cfg_attr(test, test)]
    fn validated_corridor_screen_is_attributed_and_keeps_all_survivors() {
        let declaration = corridor_declaration();
        let verdict = screen_validated_corridor_candidates(
            declaration.clone(),
            CorridorValidatedScreenRequest {
                schema_version: CORRIDOR_VALIDATED_SCREEN_SCHEMA.into(),
                candidates: corridor_measurements(&declaration),
                route_budget: 1,
            },
        )
        .expect("valid complete measurement set");
        assert_eq!(verdict.evaluated_count, 2);
        assert_eq!(verdict.clearance_creepage_prefilter_subset.len(), 1);
        let rejected = verdict
            .results
            .iter()
            .find(|row| !row.vetoes.is_empty())
            .expect("one candidate should be vetoed");
        assert_eq!(
            rejected.vetoes[0].authority_key,
            "clearance.hv_lv.project.target"
        );
        assert_eq!(
            rejected.vetoes[0].authority_role,
            temper_design_bundle::safety_value_authority::AuthorityRole::ConservativeDesignTarget
        );
    }

    #[cfg_attr(test, test)]
    fn validated_corridor_screen_requires_exact_measurement_coverage() {
        let declaration = corridor_declaration();
        let mut measurements = corridor_measurements(&declaration);
        measurements.pop();
        let error = screen_validated_corridor_candidates(
            declaration,
            CorridorValidatedScreenRequest {
                schema_version: CORRIDOR_VALIDATED_SCREEN_SCHEMA.into(),
                candidates: measurements,
                route_budget: 1,
            },
        )
        .expect_err("partial measurement set must fail closed");
        assert!(error.contains("exact declared candidate set"));
    }

    #[cfg_attr(test, test)]
    fn validated_corridor_screen_rejects_candidate_envelope_tampering() {
        let mut declaration = corridor_declaration();
        let measurements = corridor_measurements(&declaration);
        declaration.candidates[0].route_points[0][0] += 1.0;
        let error = screen_validated_corridor_candidates(
            declaration,
            CorridorValidatedScreenRequest {
                schema_version: CORRIDOR_VALIDATED_SCREEN_SCHEMA.into(),
                candidates: measurements,
                route_budget: 1,
            },
        )
        .expect_err("tampered candidate envelope must fail closed");
        assert!(error.contains("authority-mismatched"));
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("regional_feasibility::tests::pre_route_verdict_owns_canonical_reason_order", pre_route_verdict_owns_canonical_reason_order),
        ("regional_feasibility::tests::pre_route_verdict_accepts_only_an_empty_veto_set", pre_route_verdict_accepts_only_an_empty_veto_set),
        ("regional_feasibility::tests::accepts_real_pareto_improvement", accepts_real_pareto_improvement),
        ("regional_feasibility::tests::rejects_creepage_win_that_buys_a_short", rejects_creepage_win_that_buys_a_short),
        ("regional_feasibility::tests::rejects_new_pair_even_when_counts_fall", rejects_new_pair_even_when_counts_fall),
        ("regional_feasibility::tests::rejects_body_collision_endpoint_drift_and_instrument_error", rejects_body_collision_endpoint_drift_and_instrument_error),
        ("regional_feasibility::tests::endpoint_drift_tracks_pad_identity_not_coordinate", endpoint_drift_tracks_pad_identity_not_coordinate),
        ("regional_feasibility::tests::regional_declaration_is_deterministic_and_budgeted", regional_declaration_is_deterministic_and_budgeted),
        ("regional_feasibility::tests::validated_corridor_screen_is_attributed_and_keeps_all_survivors", validated_corridor_screen_is_attributed_and_keeps_all_survivors),
        ("regional_feasibility::tests::validated_corridor_screen_requires_exact_measurement_coverage", validated_corridor_screen_requires_exact_measurement_coverage),
        ("regional_feasibility::tests::validated_corridor_screen_rejects_candidate_envelope_tampering", validated_corridor_screen_rejects_candidate_envelope_tampering),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}
