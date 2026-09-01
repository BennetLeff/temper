//! Closed admission lifecycle for the declared Net-41 corridor campaign.
//!
//! External tools own measurements. Rust owns the exact stage coverage,
//! canonical veto order, route prefix, terminal classification, and selection.

use crate::regional_feasibility::{
    CorridorDeclaration, CorridorEvidenceInputs, CorridorValidatedScreenRequest,
    validate_and_screen_corridor_evidence, validate_corridor_evidence,
};
use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet};

pub const CORRIDOR_CAMPAIGN_REQUEST_SCHEMA: &str = "temper-corridor-campaign-request/v1";
pub const CORRIDOR_CAMPAIGN_RECEIPT_SCHEMA: &str = "temper-corridor-campaign-receipt/v1";
pub const CORRIDOR_MATERIALIZATION_SCHEMA: &str = "temper-corridor-materialization-instruction/v1";
pub const CORRIDOR_MOVABLE_REFS: &[&str] = &["J1", "R45", "R58", "R66", "SW1", "U22"];
pub const CORRIDOR_AFFECTED_REFS: &[&str] = &["J1", "R14", "R45", "R58", "R66", "SW1", "U22"];

#[derive(Debug, Clone, PartialEq, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct FootprintPosition {
    pub reference: String,
    pub x_mm: f64,
    pub y_mm: f64,
    pub rotation_deg: f64,
}

#[derive(Debug, Clone, PartialEq, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct CorridorMaterializationInstruction {
    pub schema_version: String,
    pub candidate_id: String,
    pub placement_id: String,
    pub footprint_positions: Vec<FootprintPosition>,
    pub route_net: i64,
    pub route_layer: String,
    pub route_width_mm: f64,
    pub via_size_mm: f64,
    pub via_drill_mm: f64,
    pub via_span: Vec<String>,
    pub fixed_ref: String,
    pub fixed_pad_number: String,
    pub moving_ref: String,
    pub moving_pad_number: String,
    pub old_segment_tstamps: Vec<String>,
    pub old_via_tstamp: String,
    pub route_points: Vec<[f64; 2]>,
}

#[derive(Deserialize)]
struct BoundCampaignDeclaration {
    family: BoundCampaignFamily,
    route: BoundCampaignRoute,
}

#[derive(Deserialize)]
struct BoundCampaignFamily {
    layer: String,
    route_width_mm: f64,
    via_diameter_mm: f64,
    via_drill_mm: f64,
    via_span: Vec<String>,
}

#[derive(Deserialize)]
struct BoundCampaignRoute {
    net_index: i64,
    existing_segment_tstamps: Vec<String>,
    existing_via: BoundCampaignVia,
}

#[derive(Deserialize)]
struct BoundCampaignVia {
    tstamp: String,
}

#[derive(Deserialize)]
struct PredecessorRows {
    results: Vec<PredecessorRow>,
}

#[derive(Deserialize)]
struct PredecessorRow {
    predecessor_placement_id: String,
    east_shift_mm: f64,
    placements: BTreeMap<String, [f64; 3]>,
}

/// Derive the only accepted board mutation instruction for one candidate.
///
/// Python transports this value to the exact S-expression writer. It does not
/// reconstruct candidate geometry, placements, route identities, or layers.
pub fn corridor_materialization_instruction(
    evidence: &CorridorEvidenceInputs<'_>,
    candidate_id: &str,
) -> Result<CorridorMaterializationInstruction, String> {
    let candidate_set = validate_corridor_evidence(evidence)?;
    let candidate = candidate_set
        .candidates
        .iter()
        .find(|row| row.candidate_id == candidate_id)
        .ok_or_else(|| "candidate is not a member of the validated declaration".to_string())?;
    let bound: BoundCampaignDeclaration = serde_json::from_str(evidence.declaration_json)
        .map_err(|error| format!("invalid campaign declaration: {error}"))?;
    let predecessor: PredecessorRows = serde_json::from_str(evidence.predecessor_manifest_json)
        .map_err(|error| format!("invalid predecessor manifest: {error}"))?;
    let matching: Vec<_> = predecessor
        .results
        .iter()
        .filter(|row| {
            row.predecessor_placement_id == candidate.placement_id && row.east_shift_mm == 4.0
        })
        .collect();
    let parent = match matching.as_slice() {
        [row] => *row,
        [] => return Err("candidate predecessor placement is absent".into()),
        _ => return Err("candidate predecessor placement is ambiguous".into()),
    };
    let mut footprint_positions = Vec::with_capacity(CORRIDOR_MOVABLE_REFS.len() + 1);
    for reference in CORRIDOR_MOVABLE_REFS {
        let [x_mm, y_mm, rotation_deg] = parent
            .placements
            .get(*reference)
            .copied()
            .ok_or_else(|| format!("predecessor placement is missing {reference}"))?;
        footprint_positions.push(FootprintPosition {
            reference: (*reference).to_string(),
            x_mm,
            y_mm,
            rotation_deg,
        });
    }
    footprint_positions.push(FootprintPosition {
        reference: "R14".into(),
        x_mm: candidate.endpoint_x_mm,
        y_mm: 249.56,
        rotation_deg: 270.0,
    });
    Ok(CorridorMaterializationInstruction {
        schema_version: CORRIDOR_MATERIALIZATION_SCHEMA.into(),
        candidate_id: candidate.candidate_id.clone(),
        placement_id: candidate.placement_id.clone(),
        footprint_positions,
        route_net: bound.route.net_index,
        route_layer: bound.family.layer,
        route_width_mm: bound.family.route_width_mm,
        via_size_mm: bound.family.via_diameter_mm,
        via_drill_mm: bound.family.via_drill_mm,
        via_span: bound.family.via_span,
        fixed_ref: "C7".into(),
        fixed_pad_number: "1".into(),
        moving_ref: "R14".into(),
        moving_pad_number: "2".into(),
        old_segment_tstamps: bound.route.existing_segment_tstamps,
        old_via_tstamp: bound.route.existing_via.tstamp,
        route_points: candidate.route_points.clone(),
    })
}

pub fn validate_corridor_materialization_instruction(
    evidence: &CorridorEvidenceInputs<'_>,
    submitted: CorridorMaterializationInstruction,
) -> Result<CorridorMaterializationInstruction, String> {
    if submitted.schema_version != CORRIDOR_MATERIALIZATION_SCHEMA {
        return Err("unsupported corridor materialization schema".into());
    }
    let expected = corridor_materialization_instruction(evidence, &submitted.candidate_id)?;
    if submitted != expected {
        return Err("materialization instruction does not match the Rust-derived candidate".into());
    }
    Ok(expected)
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Deserialize, Serialize)]
#[serde(rename_all = "kebab-case")]
pub enum InstrumentState {
    Trusted,
    Indeterminate,
    Error,
}

#[derive(Debug, Clone, PartialEq, Eq, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct InstrumentEvidence {
    pub name: String,
    pub state: InstrumentState,
    pub detail: String,
    pub subject_sha256: String,
    pub receipt_sha256: String,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Deserialize, Serialize)]
#[serde(rename_all = "kebab-case")]
pub enum DrcCategoryState {
    UncappedExact,
    RawSaturatedScopedComplete,
    RawSaturatedUnresolved,
}

#[derive(Debug, Clone, PartialEq, Eq, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct AdmissionEvidence {
    pub connected: bool,
    pub complete_selv_denominator: bool,
    pub new_safety_signature_count: usize,
    pub worsened_safety_signature_count: usize,
    pub route_geometry_valid: bool,
    pub current_capacity_valid: bool,
    pub containment_failure_count: usize,
    pub new_body_overlap_count: usize,
    pub worsened_body_overlap_count: usize,
    pub new_courtyard_overlap_count: usize,
    pub worsened_courtyard_overlap_count: usize,
    pub mutation_scope_valid: bool,
    pub drc_category_states: BTreeMap<String, DrcCategoryState>,
    pub drc_semantic_repeats_agree: bool,
    pub drc_new_hard_observation_count: usize,
    pub drc_worsened_hard_observation_count: usize,
    pub drc_indeterminate_hard_comparison_count: usize,
    pub drc_new_scoped_silk_finding_count: usize,
    pub netlist_reconciled: bool,
}

#[derive(Debug, Clone, PartialEq, Eq, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct MaterializedCandidateEvidence {
    pub candidate_id: String,
    pub scratch_board_sha256: String,
    pub instrument_state: InstrumentState,
    pub instrument_detail: String,
    pub receipts: Vec<InstrumentEvidence>,
    pub admission: AdmissionEvidence,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Deserialize, Serialize)]
#[serde(rename_all = "kebab-case")]
pub enum RouteExecutionState {
    Conclusive,
    Indeterminate,
    InstrumentError,
}

#[derive(Debug, Clone, PartialEq, Eq, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct RoutedCandidateEvidence {
    pub candidate_id: String,
    pub input_board_sha256: String,
    pub routed_board_sha256: Option<String>,
    pub execution_state: RouteExecutionState,
    pub detail: String,
    pub router_reported_complete: bool,
    pub pad_connectivity_complete: bool,
    pub receipts: Vec<InstrumentEvidence>,
    pub admission: AdmissionEvidence,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct CorridorCampaignRequest {
    pub schema_version: String,
    pub screening: CorridorValidatedScreenRequest,
    pub preflight: Vec<InstrumentEvidence>,
    pub materialized: Vec<MaterializedCandidateEvidence>,
    pub routed: Vec<RoutedCandidateEvidence>,
    pub production_board_sha256_after: String,
    pub drc_ceiling_sha256_before: String,
    pub drc_ceiling_sha256_after: String,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Deserialize, Serialize)]
#[serde(rename_all = "kebab-case")]
pub enum TerminalStatus {
    Completed,
    Exhausted,
    StoppedIndeterminate,
    InstrumentError,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct CandidateAdmissionRecord {
    pub candidate_id: String,
    pub scratch_board_sha256: String,
    pub accepted: bool,
    pub vetoes: Vec<String>,
    pub instrument_state: InstrumentState,
    pub instrument_detail: String,
    pub receipts: Vec<InstrumentEvidence>,
    pub admission: AdmissionEvidence,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct RoutedAdmissionRecord {
    pub candidate_id: String,
    pub input_board_sha256: String,
    pub routed_board_sha256: Option<String>,
    pub passed: bool,
    pub vetoes: Vec<String>,
    pub execution_state: RouteExecutionState,
    pub detail: String,
    pub receipts: Vec<InstrumentEvidence>,
    pub admission: AdmissionEvidence,
}

#[derive(Debug, Serialize)]
pub struct CorridorCampaignReceipt {
    pub schema_version: &'static str,
    pub status: TerminalStatus,
    pub reason: String,
    pub declaration_hash: String,
    pub candidate_set_digest: String,
    pub production_board_sha256_before: String,
    pub production_board_sha256_after: String,
    pub drc_ceiling_sha256_before: String,
    pub drc_ceiling_sha256_after: String,
    pub declared_count: usize,
    pub measured_count: usize,
    pub prefilter_survivor_count: usize,
    pub materialized_count: usize,
    pub pre_route_survivor_count: usize,
    pub routed_count: usize,
    pub admitted_count: usize,
    pub untested_eligible_count: usize,
    pub preflight: Vec<InstrumentEvidence>,
    pub materialized: Vec<CandidateAdmissionRecord>,
    pub routed: Vec<RoutedAdmissionRecord>,
    pub selected_candidate_id: Option<String>,
    pub selected_board_sha256: Option<String>,
}

fn valid_digest(value: &str) -> bool {
    value.len() == 64 && value.bytes().all(|byte| byte.is_ascii_hexdigit())
}

const PREFLIGHT_INSTRUMENTS: &[&str] = &[
    "baseline-kicad-drc",
    "pcbnew-rotation-oracle",
    "pyo3-extensions",
];

const PRE_ROUTE_INSTRUMENTS: &[&str] = &[
    "body-courtyard-overlap",
    "connectivity",
    "containment",
    "mutation-scope",
    "normalized-kicad-drc",
    "route-geometry-current-capacity",
    "safety-signatures",
    "selv-denominator",
];

const POST_ROUTE_INSTRUMENTS: &[&str] = &[
    "body-courtyard-overlap",
    "connectivity",
    "containment",
    "mutation-scope",
    "netlist-reconciliation",
    "normalized-kicad-drc",
    "pad-connectivity",
    "route-geometry-current-capacity",
    "router-completion",
    "safety-signatures",
    "selv-denominator",
];

fn validate_instrument_set(
    rows: &[InstrumentEvidence],
    expected: &[&str],
    subject_sha256: &str,
) -> Result<(), String> {
    if !valid_digest(subject_sha256) {
        return Err("instrument subject must be a 64-character hexadecimal digest".into());
    }
    let mut names = BTreeSet::new();
    for row in rows {
        if row.name.trim().is_empty()
            || row.detail.trim().is_empty()
            || !names.insert(row.name.as_str())
            || row.subject_sha256 != subject_sha256
            || !valid_digest(&row.receipt_sha256)
        {
            return Err(
                "instrument evidence must have unique names, detail, a matching subject, and a valid receipt hash".into(),
            );
        }
    }
    let expected_names: BTreeSet<_> = expected.iter().copied().collect();
    if names != expected_names {
        return Err(format!(
            "instrument set mismatch: expected {expected_names:?}, got {names:?}"
        ));
    }
    Ok(())
}

fn aggregate_instrument_state(rows: &[InstrumentEvidence]) -> InstrumentState {
    if rows.iter().any(|row| row.state == InstrumentState::Error) {
        InstrumentState::Error
    } else if rows
        .iter()
        .any(|row| row.state == InstrumentState::Indeterminate)
    {
        InstrumentState::Indeterminate
    } else {
        InstrumentState::Trusted
    }
}

fn admission_vetoes(input: &AdmissionEvidence, require_netlist: bool) -> Vec<String> {
    let mut reasons = Vec::new();
    if !input.connected {
        reasons.push("connectivity".into());
    }
    if !input.complete_selv_denominator {
        reasons.push("complete_selv_denominator".into());
    }
    if input.new_safety_signature_count > 0 {
        reasons.push("new_safety_signature".into());
    }
    if input.worsened_safety_signature_count > 0 {
        reasons.push("worsened_safety_signature".into());
    }
    if !input.route_geometry_valid {
        reasons.push("route_geometry".into());
    }
    if !input.current_capacity_valid {
        reasons.push("current_capacity".into());
    }
    if input.containment_failure_count > 0 {
        reasons.push("containment".into());
    }
    if input.new_body_overlap_count > 0 || input.worsened_body_overlap_count > 0 {
        reasons.push("body_overlap".into());
    }
    if input.new_courtyard_overlap_count > 0 || input.worsened_courtyard_overlap_count > 0 {
        reasons.push("courtyard_overlap".into());
    }
    if !input.mutation_scope_valid {
        reasons.push("mutation_scope".into());
    }
    if input.drc_category_states.is_empty()
        || input
            .drc_category_states
            .values()
            .any(|state| *state == DrcCategoryState::RawSaturatedUnresolved)
    {
        reasons.push("drc_cap".into());
    }
    if input.drc_category_states.iter().any(|(category, state)| {
        *state == DrcCategoryState::RawSaturatedScopedComplete
            && category.strip_prefix("W:").unwrap_or(category) != "silk_overlap"
    }) {
        reasons.push("drc_scope".into());
    }
    if !input.drc_semantic_repeats_agree {
        reasons.push("drc_repeat_disagreement".into());
    }
    if input.drc_new_hard_observation_count > 0 || input.drc_worsened_hard_observation_count > 0 {
        reasons.push("drc_hard_rule".into());
    }
    if input.drc_indeterminate_hard_comparison_count > 0 {
        reasons.push("drc_hard_indeterminate".into());
    }
    if input.drc_new_scoped_silk_finding_count > 0 {
        reasons.push("drc_scoped_silk".into());
    }
    if require_netlist && !input.netlist_reconciled {
        reasons.push("netlist_reconciliation".into());
    }
    reasons
}

fn base_receipt(
    declaration: &CorridorDeclaration,
    request: &CorridorCampaignRequest,
) -> CorridorCampaignReceipt {
    CorridorCampaignReceipt {
        schema_version: CORRIDOR_CAMPAIGN_RECEIPT_SCHEMA,
        status: TerminalStatus::StoppedIndeterminate,
        reason: String::new(),
        declaration_hash: declaration.declaration_hash.clone(),
        candidate_set_digest: declaration.candidate_set_digest.clone(),
        production_board_sha256_before: declaration.board_hash.clone(),
        production_board_sha256_after: request.production_board_sha256_after.clone(),
        drc_ceiling_sha256_before: request.drc_ceiling_sha256_before.clone(),
        drc_ceiling_sha256_after: request.drc_ceiling_sha256_after.clone(),
        declared_count: declaration.candidate_count,
        measured_count: 0,
        prefilter_survivor_count: 0,
        materialized_count: 0,
        pre_route_survivor_count: 0,
        routed_count: 0,
        admitted_count: 0,
        untested_eligible_count: 0,
        preflight: request.preflight.clone(),
        materialized: Vec::new(),
        routed: Vec::new(),
        selected_candidate_id: None,
        selected_board_sha256: None,
    }
}

/// Validate the complete campaign submission and emit one terminal receipt.
pub fn execute_corridor_campaign(
    evidence: &CorridorEvidenceInputs<'_>,
    request: CorridorCampaignRequest,
) -> Result<CorridorCampaignReceipt, String> {
    if request.schema_version != CORRIDOR_CAMPAIGN_REQUEST_SCHEMA {
        return Err("unsupported corridor campaign request schema".into());
    }
    if !valid_digest(&request.production_board_sha256_after)
        || !valid_digest(&request.drc_ceiling_sha256_before)
        || !valid_digest(&request.drc_ceiling_sha256_after)
    {
        return Err("campaign authority hashes must be 64-character hexadecimal digests".into());
    }
    if request.screening.route_budget != 12 {
        return Err("corridor execution requires the declaration's route budget of 12".into());
    }
    let declaration = validate_corridor_evidence(evidence)?;
    validate_instrument_set(
        &request.preflight,
        PREFLIGHT_INSTRUMENTS,
        &declaration.board_hash,
    )?;
    let mut receipt = base_receipt(&declaration, &request);

    if request.production_board_sha256_after != receipt.production_board_sha256_before
        || request.drc_ceiling_sha256_after != request.drc_ceiling_sha256_before
    {
        return Err("scratch-only campaign changed a production authority".into());
    }

    if let Some(failed) = request
        .preflight
        .iter()
        .find(|row| row.state != InstrumentState::Trusted)
    {
        receipt.status = TerminalStatus::InstrumentError;
        receipt.reason = format!("preflight {}: {}", failed.name, failed.detail);
        return Ok(receipt);
    }

    let screen = validate_and_screen_corridor_evidence(evidence, request.screening.clone())?;
    receipt.measured_count = screen.evaluated_count;
    receipt.prefilter_survivor_count = screen.clearance_creepage_prefilter_subset.len();

    let expected = &screen.clearance_creepage_prefilter_subset;
    let actual: Vec<_> = request
        .materialized
        .iter()
        .map(|row| row.candidate_id.as_str())
        .collect();
    if actual != expected.iter().map(String::as_str).collect::<Vec<_>>() {
        return Err(
            "materialized evidence must cover every ordered prefilter survivor exactly".into(),
        );
    }

    let mut pre_route_ids = Vec::new();
    let mut indeterminate_materialization = None;
    for row in request.materialized {
        if row.candidate_id.trim().is_empty()
            || !valid_digest(&row.scratch_board_sha256)
            || row.instrument_detail.trim().is_empty()
        {
            return Err("materialized candidate identity, hash, and detail are required".into());
        }
        validate_instrument_set(
            &row.receipts,
            PRE_ROUTE_INSTRUMENTS,
            &row.scratch_board_sha256,
        )?;
        let derived_state = aggregate_instrument_state(&row.receipts);
        if row.instrument_state != derived_state {
            return Err("materialized instrument state does not match its named receipts".into());
        }
        let vetoes = admission_vetoes(&row.admission, false);
        let accepted = derived_state == InstrumentState::Trusted && vetoes.is_empty();
        if row.instrument_state != InstrumentState::Trusted
            && indeterminate_materialization.is_none()
        {
            indeterminate_materialization = Some(format!(
                "materialization {}: {}",
                row.candidate_id, row.instrument_detail
            ));
        }
        if accepted {
            pre_route_ids.push((row.candidate_id.clone(), row.scratch_board_sha256.clone()));
        }
        let admission = row.admission;
        receipt.materialized.push(CandidateAdmissionRecord {
            candidate_id: row.candidate_id,
            scratch_board_sha256: row.scratch_board_sha256,
            accepted,
            vetoes,
            instrument_state: row.instrument_state,
            instrument_detail: row.instrument_detail,
            receipts: row.receipts,
            admission,
        });
    }
    receipt.materialized_count = receipt.materialized.len();
    receipt.pre_route_survivor_count = pre_route_ids.len();
    if let Some(reason) = indeterminate_materialization {
        receipt.status = TerminalStatus::StoppedIndeterminate;
        receipt.reason = reason;
        receipt.untested_eligible_count = pre_route_ids.len();
        return Ok(receipt);
    }

    let route_limit = 12.min(screen.clearance_creepage_prefilter_subset.len());
    let expected_route_ids: Vec<_> = pre_route_ids
        .iter()
        .take(route_limit)
        .map(|(id, _)| id.as_str())
        .collect();
    let routed_ids: Vec<_> = request
        .routed
        .iter()
        .map(|row| row.candidate_id.as_str())
        .collect();
    if routed_ids.len() > expected_route_ids.len()
        || routed_ids != expected_route_ids[..routed_ids.len()]
    {
        return Err("routed evidence must be the exact deterministic route prefix".into());
    }

    let mut selected = None;
    let mut unresolved = None;
    for (index, row) in request.routed.into_iter().enumerate() {
        if selected.is_some() {
            return Err("routed evidence must stop at the first admitted route".into());
        }
        if !valid_digest(&row.input_board_sha256)
            || row
                .routed_board_sha256
                .as_deref()
                .is_some_and(|hash| !valid_digest(hash))
            || row.detail.trim().is_empty()
            || row.input_board_sha256 != pre_route_ids[index].1
        {
            return Err("routed candidate hashes, detail, or input identity are invalid".into());
        }
        let receipt_subject = row
            .routed_board_sha256
            .as_deref()
            .unwrap_or(&row.input_board_sha256);
        validate_instrument_set(&row.receipts, POST_ROUTE_INSTRUMENTS, receipt_subject)?;
        let receipt_state = aggregate_instrument_state(&row.receipts);
        let expected_execution_state = match receipt_state {
            InstrumentState::Trusted => RouteExecutionState::Conclusive,
            InstrumentState::Indeterminate => RouteExecutionState::Indeterminate,
            InstrumentState::Error => RouteExecutionState::InstrumentError,
        };
        if row.execution_state != expected_execution_state {
            return Err("route execution state does not match its named receipts".into());
        }
        let mut vetoes = admission_vetoes(&row.admission, true);
        if !row.router_reported_complete {
            vetoes.push("router_completion".into());
        }
        if !row.pad_connectivity_complete {
            vetoes.push("pad_connectivity".into());
        }
        let passed = row.execution_state == RouteExecutionState::Conclusive
            && row.routed_board_sha256.is_some()
            && vetoes.is_empty();
        if row.execution_state != RouteExecutionState::Conclusive && unresolved.is_none() {
            unresolved = Some(format!("routing {}: {}", row.candidate_id, row.detail));
        }
        if passed && selected.is_none() && unresolved.is_none() {
            selected = Some((row.candidate_id.clone(), row.routed_board_sha256.clone()));
        }
        let admission = row.admission;
        receipt.routed.push(RoutedAdmissionRecord {
            candidate_id: row.candidate_id,
            input_board_sha256: row.input_board_sha256,
            routed_board_sha256: row.routed_board_sha256,
            passed,
            vetoes,
            execution_state: row.execution_state,
            detail: row.detail,
            receipts: row.receipts,
            admission,
        });
    }
    receipt.routed_count = receipt.routed.len();
    receipt.admitted_count = receipt.routed.iter().filter(|row| row.passed).count();

    if let Some((candidate_id, board_hash)) = selected {
        receipt.status = TerminalStatus::Completed;
        receipt.reason = "highest-ranked conclusively admitted route selected".into();
        receipt.selected_candidate_id = Some(candidate_id);
        receipt.selected_board_sha256 = board_hash;
        receipt.untested_eligible_count = pre_route_ids.len().saturating_sub(receipt.routed_count);
        return Ok(receipt);
    }
    if let Some(reason) = unresolved {
        receipt.status = TerminalStatus::StoppedIndeterminate;
        receipt.reason = reason;
        receipt.untested_eligible_count = pre_route_ids.len().saturating_sub(receipt.routed_count);
        return Ok(receipt);
    }
    if receipt.routed_count < expected_route_ids.len() {
        receipt.status = TerminalStatus::StoppedIndeterminate;
        receipt.reason = "eligible route prefix is incomplete".into();
        receipt.untested_eligible_count = pre_route_ids.len().saturating_sub(receipt.routed_count);
        return Ok(receipt);
    }
    receipt.untested_eligible_count = pre_route_ids.len().saturating_sub(receipt.routed_count);
    if receipt.untested_eligible_count == 0 {
        receipt.status = TerminalStatus::Exhausted;
        receipt.reason = "all declared candidates have conclusive outcomes and none passed".into();
    } else {
        receipt.status = TerminalStatus::StoppedIndeterminate;
        receipt.reason = "route budget leaves eligible candidates untested".into();
    }
    Ok(receipt)
}

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

    fn admission(pass: bool) -> AdmissionEvidence {
        AdmissionEvidence {
            connected: pass,
            complete_selv_denominator: pass,
            new_safety_signature_count: 0,
            worsened_safety_signature_count: 0,
            route_geometry_valid: pass,
            current_capacity_valid: pass,
            containment_failure_count: 0,
            new_body_overlap_count: 0,
            worsened_body_overlap_count: 0,
            new_courtyard_overlap_count: 0,
            worsened_courtyard_overlap_count: 0,
            mutation_scope_valid: pass,
            drc_category_states: BTreeMap::from([(
                "clearance".into(),
                DrcCategoryState::UncappedExact,
            )]),
            drc_semantic_repeats_agree: pass,
            drc_new_hard_observation_count: 0,
            drc_worsened_hard_observation_count: 0,
            drc_indeterminate_hard_comparison_count: 0,
            drc_new_scoped_silk_finding_count: 0,
            netlist_reconciled: pass,
        }
    }

    #[cfg_attr(test, test)]
    fn admission_veto_order_is_canonical() {
        let vetoes = admission_vetoes(
            &AdmissionEvidence {
                connected: false,
                complete_selv_denominator: false,
                new_safety_signature_count: 1,
                worsened_safety_signature_count: 1,
                route_geometry_valid: false,
                current_capacity_valid: false,
                containment_failure_count: 1,
                new_body_overlap_count: 1,
                worsened_body_overlap_count: 0,
                new_courtyard_overlap_count: 1,
                worsened_courtyard_overlap_count: 0,
                mutation_scope_valid: false,
                drc_category_states: BTreeMap::from([
                    ("clearance".into(), DrcCategoryState::RawSaturatedUnresolved),
                    (
                        "creepage".into(),
                        DrcCategoryState::RawSaturatedScopedComplete,
                    ),
                ]),
                drc_semantic_repeats_agree: false,
                drc_new_hard_observation_count: 1,
                drc_worsened_hard_observation_count: 1,
                drc_indeterminate_hard_comparison_count: 1,
                drc_new_scoped_silk_finding_count: 1,
                netlist_reconciled: false,
            },
            true,
        );
        assert_eq!(
            vetoes,
            vec![
                "connectivity",
                "complete_selv_denominator",
                "new_safety_signature",
                "worsened_safety_signature",
                "route_geometry",
                "current_capacity",
                "containment",
                "body_overlap",
                "courtyard_overlap",
                "mutation_scope",
                "drc_cap",
                "drc_scope",
                "drc_repeat_disagreement",
                "drc_hard_rule",
                "drc_hard_indeterminate",
                "drc_scoped_silk",
                "netlist_reconciliation",
            ]
        );
    }

    #[cfg_attr(test, test)]
    fn passing_admission_has_no_vetoes() {
        assert!(admission_vetoes(&admission(true), true).is_empty());
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("corridor_campaign::tests::admission_veto_order_is_canonical", admission_veto_order_is_canonical),
        ("corridor_campaign::tests::passing_admission_has_no_vetoes", passing_admission_has_no_vetoes),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}
