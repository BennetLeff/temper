//! Rust-owned prepare/finalize boundary for pre-route corridor feasibility.
//!
//! This protocol is intentionally separate from the historical campaign-v1
//! receipt. It validates an immutable family and requests one witness, but it
//! has no route call graph and no caller-controlled family certificate.

mod contract;
pub use contract::*;

use crate::corridor_campaign::{
    CORRIDOR_AFFECTED_REFS, CORRIDOR_MATERIALIZATION_SCHEMA, InstrumentEvidence, InstrumentState,
    corridor_materialization_instruction, valid_digest,
};
use crate::regional_feasibility::{
    CorridorEvidenceInputs, CorridorValidatedScreenRequest, validate_and_screen_corridor_evidence,
    validate_corridor_evidence,
};
use serde::Serialize;
use std::collections::{BTreeMap, BTreeSet};

#[derive(Serialize)]
struct CheckEvidencePayload<'a> {
    evaluation: EvaluationState,
    trust: TrustState,
    findings: &'a [FindingIdentity],
    receipt_sha256: &'a Option<String>,
}

fn check_payload_sha256(check: &CheckEvidence) -> Result<String, String> {
    let payload = CheckEvidencePayload {
        evaluation: check.evaluation,
        trust: check.trust,
        findings: &check.findings,
        receipt_sha256: &check.receipt_sha256,
    };
    let bytes = serde_json::to_vec(&payload).map_err(|error| error.to_string())?;
    temper_design_bundle::regional_topology::candidate_digest(&bytes)
}

fn validate_authorities(
    a: &FeasibilityAuthorities,
    board: &str,
    generated: &[String],
) -> Result<(), String> {
    if !valid_digest(&a.production_board_sha256)
        || a.production_board_sha256 != board
        || !valid_digest(&a.drc_ceiling_sha256)
        || !valid_digest(&a.tool_context_sha256)
        || a.model_source_sha256s.is_empty()
        || a.model_source_sha256s.iter().any(|v| !valid_digest(v))
    {
        return Err("authority hashes are invalid or do not bind the declaration".into());
    }
    let mut supplied = a.generated_input_sha256s.clone();
    supplied.sort();
    if supplied != generated
        || supplied.windows(2).any(|w| w[0] == w[1])
        || supplied.iter().any(|v| !valid_digest(v))
    {
        return Err("generated-input authorities do not exactly bind the declaration".into());
    }
    Ok(())
}

fn validate_check(name: &str, check: &CheckEvidence) -> Result<(), String> {
    validate_check_inner(name, check, true)
}

fn validate_check_unsealed(name: &str, check: &CheckEvidence) -> Result<(), String> {
    validate_check_inner(name, check, false)
}

fn validate_check_inner(
    name: &str,
    check: &CheckEvidence,
    require_seal: bool,
) -> Result<(), String> {
    match check.evaluation {
        EvaluationState::NotEvaluated
            if check.trust == TrustState::Trusted
                || !check.findings.is_empty()
                || (check.trust == TrustState::Indeterminate && check.receipt_sha256.is_some())
                || (check.trust == TrustState::Error && check.receipt_sha256.is_none()) =>
        {
            return Err(format!("{name}: not-evaluated has an evaluated payload"));
        }
        EvaluationState::CompletedClean
            if !check.findings.is_empty()
                || check.receipt_sha256.is_none()
                || check.trust == TrustState::Error =>
        {
            return Err(format!("{name}: completed-clean payload is inconsistent"));
        }
        EvaluationState::CompletedWithFindings
            if check.findings.is_empty() || check.receipt_sha256.is_none() =>
        {
            return Err(format!(
                "{name}: completed-with-findings payload is inconsistent"
            ));
        }
        _ => {}
    }
    if let Some(receipt) = &check.receipt_sha256
        && !valid_digest(receipt)
    {
        return Err(format!("{name}: receipt hash is invalid"));
    }
    match check.evidence_payload_sha256.as_deref() {
        Some(digest) if check.evaluation == EvaluationState::NotEvaluated => {
            let _ = digest;
            return Err(format!(
                "{name}: not-evaluated evidence has a payload digest"
            ));
        }
        Some(digest) if valid_digest(digest) => {
            let expected = check_payload_sha256(check)?;
            if digest != expected {
                return Err(format!(
                    "{name}: evidence payload digest does not match payload"
                ));
            }
        }
        Some(_) => return Err(format!("{name}: evidence payload digest is invalid")),
        None if require_seal && check.evaluation != EvaluationState::NotEvaluated => {
            return Err(format!("{name}: evaluated evidence needs a payload digest"));
        }
        None => {}
    }
    let allowed = match name {
        "safety" => Some(FindingCategory::Safety),
        "drc" => Some(FindingCategory::Drc),
        "containment" | "netlist_reconciliation" => None,
        "body_overlap" => Some(FindingCategory::BodyOverlap),
        "courtyard_overlap" => Some(FindingCategory::CourtyardOverlap),
        "connectivity" | "route_geometry" | "current_capacity" | "selv_denominator"
        | "mutation_scope" => Some(FindingCategory::GateFailure),
        // The sealing helper validates a standalone typed check before the
        // caller binds it to one of the pre-route fields. Its category is
        // therefore intentionally checked by the eventual field validator.
        _ => None,
    };
    let mut identities = BTreeSet::new();
    for finding in &check.findings {
        if finding.identity.trim().is_empty()
            || finding.multiplicity == 0
            || !identities.insert((finding.category, finding.identity.as_str()))
            || (allowed.is_some() && Some(finding.category) != allowed)
            || (name == "containment"
                && !matches!(
                    finding.category,
                    FindingCategory::ContainmentMissingModel
                        | FindingCategory::ContainmentOutsideBoard
                ))
            || name == "netlist_reconciliation"
        {
            return Err(format!(
                "{name}: finding identities have an invalid type or multiplicity"
            ));
        }
    }
    Ok(())
}

/// Add the canonical Rust-owned digest to an unsealed check payload.
///
/// A seal is deliberately write-once: callers cannot supply a digest and ask
/// Rust to bless it, even when it happens to match today.
pub fn seal_check_evidence(mut check: CheckEvidence) -> Result<CheckEvidence, String> {
    if check.evidence_payload_sha256.is_some() {
        return Err("check evidence is already sealed".into());
    }
    validate_check_unsealed("check", &check)?;
    if check.evaluation != EvaluationState::NotEvaluated {
        check.evidence_payload_sha256 = Some(check_payload_sha256(&check)?);
    }
    validate_check("check", &check)?;
    Ok(check)
}

fn diagnostic_for(check: &str, finding: &FindingIdentity) -> FindingDiagnostic {
    let (dependency, candidate_dimensions) = match (check, finding.category) {
        // Missing model inputs are shared by construction: no placement or
        // route can supply the absent geometry/denominator.
        (_, FindingCategory::ContainmentMissingModel) => {
            (FindingDependency::FamilyInvariant, Vec::new())
        }
        ("body_overlap" | "courtyard_overlap" | "containment", _) => (
            FindingDependency::PlacementDependent,
            vec!["placement".into()],
        ),
        ("route_geometry", _) => (
            FindingDependency::RouteShapeDependent,
            vec!["route-shape".into()],
        ),
        ("selv_denominator", _) => (
            FindingDependency::Unresolved,
            vec!["placement".into(), "route-shape".into()],
        ),
        // Connectivity and capacity can depend on route topology and the
        // instrument's model.  Without a registered declaration-bound proof,
        // classify them conservatively and never authorize FamilyNegative.
        _ => (
            FindingDependency::Unresolved,
            vec!["placement".into(), "route-shape".into()],
        ),
    };
    FindingDiagnostic {
        category: finding.category,
        identity: finding.identity.clone(),
        multiplicity: finding.multiplicity,
        dependency,
        candidate_dimensions,
    }
}

fn canonical_diagnostics(evidence: &PreRouteEvidence) -> Vec<FindingDiagnostic> {
    let mut diagnostics = all_checks(evidence)
        .into_iter()
        .flat_map(|(name, check)| {
            check
                .findings
                .iter()
                .map(move |finding| diagnostic_for(name, finding))
        })
        .collect::<Vec<_>>();
    diagnostics.sort_by(|a, b| {
        a.category
            .cmp(&b.category)
            .then(a.identity.cmp(&b.identity))
    });
    diagnostics
}

fn finalize_terminal(
    instrument_state: InstrumentState,
    findings: &[FindingIdentity],
) -> (FeasibilityTerminal, &'static str) {
    // Precedence is intentionally fail-closed: an instrument error or
    // indeterminate result cannot be hidden by a clean/finding payload.
    match instrument_state {
        InstrumentState::Error => (
            FeasibilityTerminal::InstrumentError,
            "a witness instrument errored",
        ),
        InstrumentState::Indeterminate => (
            FeasibilityTerminal::StoppedIndeterminate,
            "a witness instrument is indeterminate",
        ),
        InstrumentState::Trusted if !findings.is_empty() => (
            FeasibilityTerminal::WitnessRejected,
            "witness has exact pre-route findings",
        ),
        InstrumentState::Trusted => (
            FeasibilityTerminal::WitnessClean,
            "trusted witness passed every pre-route gate",
        ),
    }
}

fn all_checks(e: &PreRouteEvidence) -> [(&'static str, &CheckEvidence); 11] {
    [
        ("safety", &e.safety),
        ("drc", &e.drc),
        ("containment", &e.containment),
        ("body_overlap", &e.body_overlap),
        ("courtyard_overlap", &e.courtyard_overlap),
        ("connectivity", &e.connectivity),
        ("route_geometry", &e.route_geometry),
        ("current_capacity", &e.current_capacity),
        ("selv_denominator", &e.selv_denominator),
        ("mutation_scope", &e.mutation_scope),
        ("netlist_reconciliation", &e.netlist_reconciliation),
    ]
}

fn validate_pre_route_evidence(evidence: &PreRouteEvidence) -> Result<(), String> {
    for (name, check) in all_checks(evidence) {
        validate_check(name, check)?;
    }
    if evidence.netlist_reconciliation.evaluation != EvaluationState::NotEvaluated {
        return Err("netlist reconciliation is post-route and must be not-evaluated".into());
    }
    Ok(())
}

fn canonical_findings(evidence: &PreRouteEvidence) -> Vec<FindingIdentity> {
    let mut findings = all_checks(evidence)
        .into_iter()
        .flat_map(|(_, c)| c.findings.iter().cloned())
        .collect::<Vec<_>>();
    findings.sort_by(|a, b| {
        a.category
            .cmp(&b.category)
            .then(a.identity.cmp(&b.identity))
    });
    findings
}

pub fn summarize_findings(findings: &[FindingIdentity]) -> FindingSummary {
    let mut by_category = BTreeMap::new();
    for finding in findings {
        *by_category.entry(finding.category).or_insert(0) += finding.multiplicity;
    }
    let vetoes = by_category
        .keys()
        .map(|category| format!("{category:?}"))
        .collect();
    FindingSummary {
        total: by_category.values().sum(),
        by_category,
        vetoes,
    }
}

fn model_requirements_digest(rows: &[ModelRequirementRow]) -> Result<String, String> {
    let mut rows = rows.to_vec();
    rows.sort_by(|a, b| a.reference.cmp(&b.reference));
    temper_design_bundle::regional_topology::candidate_digest(&rows)
}

fn validate_model_requirements(
    rows: &[ModelRequirementRow],
) -> Result<Vec<FindingIdentity>, String> {
    let expected: BTreeSet<_> = CORRIDOR_AFFECTED_REFS.iter().copied().collect();
    let mut seen = BTreeSet::new();
    for row in rows {
        if row.reference.trim().is_empty() || !seen.insert(row.reference.as_str()) {
            return Err("model requirements must contain unique references".into());
        }
    }
    if seen != expected {
        return Err("model requirements must cover exactly CORRIDOR_AFFECTED_REFS".into());
    }
    let mut missing = Vec::new();
    for row in rows {
        for (field, complete) in [
            ("body_geometry", row.body_geometry),
            ("position", row.position),
            ("domain", row.domain),
            ("complete_selv_denominator", row.complete_selv_denominator),
        ] {
            if !complete {
                missing.push(FindingIdentity {
                    category: FindingCategory::ContainmentMissingModel,
                    identity: format!("{}:{field}", row.reference),
                    multiplicity: 1,
                });
            }
        }
    }
    missing.sort_by(|a, b| a.identity.cmp(&b.identity));
    Ok(missing)
}

fn validate_preflight(
    rows: &[InstrumentEvidence],
    subject: &str,
) -> Result<InstrumentState, String> {
    const EXPECTED: &[&str] = &[
        "baseline-kicad-drc",
        "pcbnew-rotation-oracle",
        "pyo3-extensions",
    ];
    if !valid_digest(subject) {
        return Err("preflight subject is not a digest".into());
    }
    let mut names = BTreeSet::new();
    for row in rows {
        if row.name.trim().is_empty()
            || row.detail.trim().is_empty()
            || !names.insert(row.name.as_str())
            || row.subject_sha256 != subject
            || !valid_digest(&row.receipt_sha256)
        {
            return Err("preflight instruments must be exact, unique, and subject-bound".into());
        }
    }
    if rows.iter().map(|row| row.name.as_str()).collect::<Vec<_>>() != EXPECTED.to_vec() {
        return Err("preflight instrument set mismatch".into());
    }
    Ok(if rows.iter().any(|r| r.state == InstrumentState::Error) {
        InstrumentState::Error
    } else if rows
        .iter()
        .any(|r| r.state == InstrumentState::Indeterminate)
    {
        InstrumentState::Indeterminate
    } else {
        InstrumentState::Trusted
    })
}

fn validate_check_instrument_bindings(
    evidence: &PreRouteEvidence,
    instruments: &[InstrumentEvidence],
) -> Result<(), String> {
    let bindings = [
        ("safety", &evidence.safety, "safety-signatures"),
        ("drc", &evidence.drc, "normalized-kicad-drc"),
        ("containment", &evidence.containment, "containment"),
        (
            "body_overlap",
            &evidence.body_overlap,
            "body-courtyard-overlap",
        ),
        (
            "courtyard_overlap",
            &evidence.courtyard_overlap,
            "body-courtyard-overlap",
        ),
        ("connectivity", &evidence.connectivity, "connectivity"),
        (
            "route_geometry",
            &evidence.route_geometry,
            "route-geometry-current-capacity",
        ),
        (
            "current_capacity",
            &evidence.current_capacity,
            "route-geometry-current-capacity",
        ),
        (
            "selv_denominator",
            &evidence.selv_denominator,
            "selv-denominator",
        ),
        ("mutation_scope", &evidence.mutation_scope, "mutation-scope"),
    ];
    for (name, check, instrument) in bindings {
        let instrument_evidence = instruments
            .iter()
            .find(|row| row.name == instrument)
            .ok_or_else(|| format!("missing instrument {instrument}"))?;
        let state = instrument_evidence.state;
        if check.evaluation != EvaluationState::NotEvaluated
            && check.receipt_sha256.as_deref() != Some(instrument_evidence.receipt_sha256.as_str())
        {
            return Err(format!(
                "{name}: evaluated evidence receipt does not match its instrument receipt"
            ));
        }
        match state {
            InstrumentState::Trusted
                if check.trust != TrustState::Trusted
                    || check.evaluation == EvaluationState::NotEvaluated =>
            {
                return Err(format!(
                    "{name}: trusted instrument has no completed evidence"
                ));
            }
            InstrumentState::Indeterminate if check.trust != TrustState::Indeterminate => {
                return Err(format!(
                    "{name}: indeterminate instrument/evidence mismatch"
                ));
            }
            InstrumentState::Error
                if check.trust != TrustState::Error
                    || check.evaluation != EvaluationState::NotEvaluated
                    || !check.findings.is_empty() =>
            {
                return Err(format!("{name}: errored instrument/evidence mismatch"));
            }
            _ => {}
        }
    }
    Ok(())
}

fn validate_prepared_receipt(
    evidence: &CorridorEvidenceInputs<'_>,
    prepared: &FeasibilityReceipt,
    authorities: &FeasibilityAuthorities,
    model_requirements: &[ModelRequirementRow],
    screening: &CorridorValidatedScreenRequest,
) -> Result<(), String> {
    if prepared.schema_version != FEASIBILITY_RECEIPT_SCHEMA
        || prepared.stage != "prepare"
        || prepared.terminal != FeasibilityTerminal::WitnessPending
        || prepared.reason != "one deterministic pre-route witness is required"
    {
        return Err("prepared receipt is not a canonical witness-pending receipt".into());
    }
    let declaration = validate_corridor_evidence(evidence)?;
    validate_authorities(
        authorities,
        &declaration.board_hash,
        &declaration.generated_input_hashes,
    )?;
    if prepared.authorities != *authorities
        || prepared.declaration_hash != declaration.declaration_hash
        || prepared.candidate_set_digest != declaration.candidate_set_digest
    {
        return Err("prepared receipt authorities or declaration binding is not canonical".into());
    }
    let model_digest = model_requirements_digest(model_requirements)?;
    if validate_model_requirements(model_requirements)?.len() != 0
        || prepared.model_requirements_sha256 != model_digest
    {
        return Err("prepared model requirements are not complete or canonical".into());
    }
    if !prepared.findings.is_empty()
        || prepared.summary != summarize_findings(&prepared.findings)
        || !prepared.diagnostics.is_empty()
        || prepared.scratch_board_sha256.is_some()
    {
        return Err(
            "prepared findings, summary, diagnostics, or scratch subject was tampered".into(),
        );
    }
    let canonical = prepare_corridor_feasibility(
        evidence,
        PrepareRequest {
            schema_version: FEASIBILITY_PREPARE_SCHEMA.into(),
            screening: screening.clone(),
            authorities: authorities.clone(),
            model_requirements: model_requirements.to_vec(),
            preflight: prepared.instruments.clone(),
        },
    )?;
    if canonical != *prepared {
        return Err("prepared receipt does not equal the canonical replay".into());
    }
    let screen = validate_and_screen_corridor_evidence(evidence, screening.clone())?;
    let board = &declaration.board_hash;
    if validate_preflight(&prepared.instruments, board)? != InstrumentState::Trusted {
        return Err("prepared preflight instruments are not a trusted canonical set".into());
    }
    let witness = prepared
        .witness
        .as_ref()
        .ok_or_else(|| "prepared receipt has no witness".to_string())?;
    require_first_screen_witness(
        &witness.candidate_id,
        &screen.clearance_creepage_prefilter_subset,
    )?;
    let candidate = declaration
        .candidates
        .iter()
        .find(|row| row.candidate_id == witness.candidate_id)
        .ok_or_else(|| "prepared witness is foreign to the declaration".to_string())?;
    let expected_instruction =
        corridor_materialization_instruction(evidence, &witness.candidate_id)?;
    let expected_instruction_digest =
        temper_design_bundle::regional_topology::candidate_digest(&expected_instruction)?;
    let expected_witness_id = format!(
        "NET41-WITNESS-{}",
        witness_digest(
            &witness.candidate_id,
            candidate.ordinal,
            &expected_instruction_digest
        )?
    );
    if witness.schema_version != FEASIBILITY_WITNESS_SCHEMA
        || witness.candidate_id != candidate.candidate_id
        || witness.declaration_ordinal != candidate.ordinal
        || witness.witness_id != expected_witness_id
        || witness.materialization_instruction != expected_instruction
        || witness.materialization_instruction_sha256 != expected_instruction_digest
    {
        return Err("prepared witness or materialization binding is not canonical".into());
    }
    Ok(())
}

fn base_receipt(
    terminal: FeasibilityTerminal,
    reason: &str,
    declaration: &crate::regional_feasibility::CorridorDeclaration,
    authorities: FeasibilityAuthorities,
    model_digest: String,
    findings: Vec<FindingIdentity>,
    instruments: Vec<InstrumentEvidence>,
) -> FeasibilityReceipt {
    FeasibilityReceipt {
        schema_version: FEASIBILITY_RECEIPT_SCHEMA.into(),
        stage: "prepare".into(),
        terminal,
        reason: reason.into(),
        declaration_hash: declaration.declaration_hash.clone(),
        candidate_set_digest: declaration.candidate_set_digest.clone(),
        authorities,
        model_requirements_sha256: model_digest,
        diagnostics: findings
            .iter()
            .map(|finding| diagnostic_for("containment", finding))
            .collect(),
        summary: summarize_findings(&findings),
        findings,
        witness: None,
        scratch_board_sha256: None,
        instruments,
    }
}

fn witness_digest(
    candidate_id: &str,
    ordinal: usize,
    instruction_digest: &str,
) -> Result<String, String> {
    temper_design_bundle::regional_topology::candidate_digest(&(
        candidate_id,
        ordinal,
        instruction_digest,
    ))
}

fn require_first_screen_witness(
    candidate_id: &str,
    ordered_survivors: &[String],
) -> Result<(), String> {
    match ordered_survivors.first() {
        Some(expected) if expected == candidate_id => Ok(()),
        Some(expected) => Err(format!(
            "prepared witness is not the first Rust-ordered survivor: expected {expected}"
        )),
        None => Err("screening produced no witness candidate; no family proof exists".into()),
    }
}

fn validate_scratch_board_subject(
    scratch_board_sha256: &str,
    production_board_sha256: &str,
) -> Result<(), String> {
    if !valid_digest(scratch_board_sha256) {
        return Err("scratch board subject is not a digest".into());
    }
    if scratch_board_sha256 == production_board_sha256 {
        return Err("scratch board subject must differ from the production board".into());
    }
    Ok(())
}

/// Validate immutable evidence and return either a truthful terminal or one deterministic witness.
pub fn prepare_corridor_feasibility(
    evidence: &CorridorEvidenceInputs<'_>,
    request: PrepareRequest,
) -> Result<FeasibilityReceipt, String> {
    if request.schema_version != FEASIBILITY_PREPARE_SCHEMA {
        return Err("unsupported feasibility prepare schema".into());
    }
    let declaration = validate_corridor_evidence(evidence)?;
    validate_authorities(
        &request.authorities,
        &declaration.board_hash,
        &declaration.generated_input_hashes,
    )?;
    let model_digest = model_requirements_digest(&request.model_requirements)?;
    let missing = validate_model_requirements(&request.model_requirements)?;
    let instrument_state = validate_preflight(&request.preflight, &declaration.board_hash)?;
    let mut receipt = base_receipt(
        FeasibilityTerminal::StoppedIndeterminate,
        "pre-route feasibility is not yet evaluated",
        &declaration,
        request.authorities,
        model_digest,
        missing.clone(),
        request.preflight.clone(),
    );
    if !missing.is_empty() {
        receipt.terminal = FeasibilityTerminal::ModelIncomplete;
        receipt.reason = "affected references have incomplete model requirements".into();
        return Ok(receipt);
    }
    if instrument_state == InstrumentState::Error {
        receipt.terminal = FeasibilityTerminal::InstrumentError;
        receipt.reason = "a required preflight instrument errored".into();
        receipt.findings = receipt
            .instruments
            .iter()
            .filter(|r| r.state == InstrumentState::Error)
            .map(|r| FindingIdentity {
                category: FindingCategory::GateFailure,
                identity: format!("preflight:{}", r.name),
                multiplicity: 1,
            })
            .collect();
        receipt.summary = summarize_findings(&receipt.findings);
        receipt.diagnostics = receipt
            .findings
            .iter()
            .map(|finding| diagnostic_for("mutation_scope", finding))
            .collect();
        return Ok(receipt);
    }
    if instrument_state == InstrumentState::Indeterminate {
        receipt.reason = "a required preflight instrument is indeterminate".into();
        return Ok(receipt);
    }
    let screen = validate_and_screen_corridor_evidence(evidence, request.screening)?;
    let Some(candidate_id) = screen.clearance_creepage_prefilter_subset.first() else {
        // A screen with no survivors is not a registered family predicate;
        // counts alone cannot authorize `family-negative`.
        receipt.reason = "screening produced no witness candidate; no family proof exists".into();
        return Ok(receipt);
    };
    let candidate = declaration
        .candidates
        .iter()
        .find(|row| row.candidate_id == *candidate_id)
        .ok_or_else(|| "screening witness is not in the declaration".to_string())?;
    let instruction = corridor_materialization_instruction(evidence, candidate_id)?;
    let instruction_digest =
        temper_design_bundle::regional_topology::candidate_digest(&instruction)?;
    let witness_id = format!(
        "NET41-WITNESS-{}",
        witness_digest(candidate_id, candidate.ordinal, &instruction_digest)?
    );
    receipt.terminal = FeasibilityTerminal::WitnessPending;
    receipt.reason = "one deterministic pre-route witness is required".into();
    receipt.witness = Some(FeasibilityWitness {
        schema_version: FEASIBILITY_WITNESS_SCHEMA.into(),
        witness_id,
        candidate_id: candidate_id.clone(),
        declaration_ordinal: candidate.ordinal,
        materialization_instruction: instruction,
        materialization_instruction_sha256: instruction_digest,
    });
    Ok(receipt)
}

/// Validate exactly the prepared witness and derive every finding summary in Rust.
pub fn finalize_corridor_feasibility(
    evidence_inputs: &CorridorEvidenceInputs<'_>,
    request: FinalizeRequest,
) -> Result<FeasibilityReceipt, String> {
    if request.schema_version != FEASIBILITY_FINALIZE_SCHEMA {
        return Err("unsupported feasibility finalize schema".into());
    }
    validate_scratch_board_subject(
        &request.scratch_board_sha256,
        &request.authorities.production_board_sha256,
    )?;
    let prepared = request.prepared;
    validate_prepared_receipt(
        evidence_inputs,
        &prepared,
        &request.authorities,
        &request.model_requirements,
        &request.screening,
    )?;
    if prepared.authorities != request.authorities {
        return Err("finalize authorities do not match the prepared receipt".into());
    }
    let declaration = validate_corridor_evidence(evidence_inputs)?;
    validate_authorities(
        &request.authorities,
        &declaration.board_hash,
        &declaration.generated_input_hashes,
    )?;
    if prepared.declaration_hash != declaration.declaration_hash
        || prepared.candidate_set_digest != declaration.candidate_set_digest
    {
        return Err("prepared receipt is foreign to the current declaration".into());
    }
    let witness = prepared
        .witness
        .clone()
        .ok_or_else(|| "prepared receipt has no witness".to_string())?;
    if request.witness_id != witness.witness_id
        || request.declaration_ordinal != witness.declaration_ordinal
        || request.materialization_instruction != witness.materialization_instruction
        || request.materialization_instruction.schema_version != CORRIDOR_MATERIALIZATION_SCHEMA
    {
        return Err("witness identity, ordinal, instruction, or subject was tampered".into());
    }
    let expected_instruction =
        corridor_materialization_instruction(evidence_inputs, &witness.candidate_id)?;
    let expected_digest =
        temper_design_bundle::regional_topology::candidate_digest(&expected_instruction)?;
    if expected_instruction != request.materialization_instruction
        || expected_digest != witness.materialization_instruction_sha256
    {
        return Err(
            "materialization instruction digest or content does not match Rust derivation".into(),
        );
    }
    let candidate = declaration
        .candidates
        .iter()
        .find(|row| row.candidate_id == witness.candidate_id)
        .ok_or_else(|| "prepared witness is foreign to the declaration".to_string())?;
    if candidate.ordinal != request.declaration_ordinal {
        return Err("witness ordinal does not match the declaration".into());
    }
    const EXPECTED: &[&str] = &[
        "body-courtyard-overlap",
        "connectivity",
        "containment",
        "mutation-scope",
        "normalized-kicad-drc",
        "route-geometry-current-capacity",
        "safety-signatures",
        "selv-denominator",
    ];
    if request.instruments.len() != EXPECTED.len()
        || request
            .instruments
            .iter()
            .any(|r| r.subject_sha256 != request.scratch_board_sha256)
    {
        return Err("finalize instrument set is not exactly subject-bound".into());
    }
    let mut names = BTreeSet::new();
    for row in &request.instruments {
        if !names.insert(row.name.as_str())
            || row.detail.trim().is_empty()
            || !valid_digest(&row.receipt_sha256)
        {
            return Err("finalize instruments must be unique and complete".into());
        }
    }
    if request
        .instruments
        .iter()
        .map(|row| row.name.as_str())
        .collect::<Vec<_>>()
        != EXPECTED.to_vec()
    {
        return Err("finalize instrument set mismatch".into());
    }
    validate_pre_route_evidence(&request.evidence)?;
    validate_check_instrument_bindings(&request.evidence, &request.instruments)?;
    let findings = canonical_findings(&request.evidence);
    let diagnostics = canonical_diagnostics(&request.evidence);
    let summary = summarize_findings(&findings);
    let instrument_state = if request
        .instruments
        .iter()
        .any(|r| r.state == InstrumentState::Error)
    {
        InstrumentState::Error
    } else if request
        .instruments
        .iter()
        .any(|r| r.state == InstrumentState::Indeterminate)
    {
        InstrumentState::Indeterminate
    } else {
        InstrumentState::Trusted
    };
    let (terminal, reason) = finalize_terminal(instrument_state, &findings);
    Ok(FeasibilityReceipt {
        schema_version: FEASIBILITY_RECEIPT_SCHEMA.into(),
        stage: "finalize".into(),
        terminal,
        reason: reason.into(),
        declaration_hash: prepared.declaration_hash,
        candidate_set_digest: prepared.candidate_set_digest,
        authorities: request.authorities,
        model_requirements_sha256: prepared.model_requirements_sha256,
        findings,
        diagnostics,
        summary,
        witness: Some(witness),
        scratch_board_sha256: Some(request.scratch_board_sha256),
        instruments: request.instruments,
    })
}

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
#[path = "tests.rs"]
pub(crate) mod tests;
