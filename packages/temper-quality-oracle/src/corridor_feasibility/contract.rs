//! Versioned request, receipt, and typed evidence contracts for corridor feasibility.

use crate::corridor_campaign::{CorridorMaterializationInstruction, InstrumentEvidence};
use crate::regional_feasibility::CorridorValidatedScreenRequest;
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;

pub const FEASIBILITY_PREPARE_SCHEMA: &str = "temper-corridor-feasibility-prepare/v1";
pub const FEASIBILITY_FINALIZE_SCHEMA: &str = "temper-corridor-feasibility-finalize/v1";
pub const FEASIBILITY_RECEIPT_SCHEMA: &str = "temper-corridor-feasibility-receipt/v1";
pub const FEASIBILITY_WITNESS_SCHEMA: &str = "temper-corridor-feasibility-witness/v1";

#[derive(Debug, Clone, Copy, PartialEq, Eq, Deserialize, Serialize)]
#[serde(rename_all = "kebab-case")]
pub enum EvaluationState {
    NotEvaluated,
    CompletedClean,
    CompletedWithFindings,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Deserialize, Serialize)]
#[serde(rename_all = "kebab-case")]
pub enum TrustState {
    Trusted,
    Indeterminate,
    Error,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Ord, PartialOrd, Deserialize, Serialize)]
#[serde(rename_all = "kebab-case")]
pub enum FindingCategory {
    Safety,
    Drc,
    ContainmentMissingModel,
    ContainmentOutsideBoard,
    BodyOverlap,
    CourtyardOverlap,
    GateFailure,
}

/// Rust-owned explanation of what a finding can depend on.  This is derived
/// from the check which produced the finding; it is deliberately absent from
/// request types so a runner cannot turn a singleton observation into a
/// family certificate.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Deserialize, Serialize)]
#[serde(rename_all = "kebab-case")]
pub enum FindingDependency {
    FamilyInvariant,
    PlacementDependent,
    RouteShapeDependent,
    Unresolved,
}

#[derive(Debug, Clone, PartialEq, Eq, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct FindingDiagnostic {
    pub category: FindingCategory,
    pub identity: String,
    pub multiplicity: usize,
    pub dependency: FindingDependency,
    /// Conservative declaration dimensions.  Empty is valid only for a
    /// family-invariant finding; every other class names the dimensions Rust
    /// cannot prove away.
    pub candidate_dimensions: Vec<String>,
}

/// Exact identity and multiplicity. Dependency/certificate labels are absent
/// by design: dependency authority is assigned only by Rust.
#[derive(Debug, Clone, PartialEq, Eq, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct FindingIdentity {
    pub category: FindingCategory,
    pub identity: String,
    pub multiplicity: usize,
}

#[derive(Debug, Clone, PartialEq, Eq, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct CheckEvidence {
    pub evaluation: EvaluationState,
    pub trust: TrustState,
    pub findings: Vec<FindingIdentity>,
    pub receipt_sha256: Option<String>,
    /// Digest of the exact typed payload above (not a digest of a separately
    /// stored receipt whose contents Rust cannot inspect).
    pub evidence_payload_sha256: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Eq, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct PreRouteEvidence {
    pub safety: CheckEvidence,
    pub drc: CheckEvidence,
    pub containment: CheckEvidence,
    pub body_overlap: CheckEvidence,
    pub courtyard_overlap: CheckEvidence,
    pub connectivity: CheckEvidence,
    pub route_geometry: CheckEvidence,
    pub current_capacity: CheckEvidence,
    pub selv_denominator: CheckEvidence,
    pub mutation_scope: CheckEvidence,
    pub netlist_reconciliation: CheckEvidence,
}

#[derive(Debug, Clone, PartialEq, Eq, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ModelRequirementRow {
    pub reference: String,
    pub body_geometry: bool,
    pub position: bool,
    pub domain: bool,
    pub complete_selv_denominator: bool,
}

#[derive(Debug, Clone, PartialEq, Eq, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct FeasibilityAuthorities {
    pub production_board_sha256: String,
    pub drc_ceiling_sha256: String,
    pub generated_input_sha256s: Vec<String>,
    pub model_source_sha256s: Vec<String>,
    pub tool_context_sha256: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct FindingSummary {
    pub total: usize,
    pub by_category: BTreeMap<FindingCategory, usize>,
    pub vetoes: Vec<String>,
}

#[derive(Debug, Clone, PartialEq, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct FeasibilityWitness {
    pub schema_version: String,
    pub witness_id: String,
    pub candidate_id: String,
    pub declaration_ordinal: usize,
    pub materialization_instruction: CorridorMaterializationInstruction,
    pub materialization_instruction_sha256: String,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Deserialize, Serialize)]
#[serde(rename_all = "kebab-case")]
pub enum FeasibilityTerminal {
    ModelIncomplete,
    InstrumentError,
    WitnessPending,
    WitnessClean,
    WitnessRejected,
    StoppedIndeterminate,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct FeasibilityReceipt {
    pub schema_version: String,
    pub stage: String,
    pub terminal: FeasibilityTerminal,
    pub reason: String,
    pub declaration_hash: String,
    pub candidate_set_digest: String,
    pub authorities: FeasibilityAuthorities,
    pub model_requirements_sha256: String,
    pub findings: Vec<FindingIdentity>,
    pub diagnostics: Vec<FindingDiagnostic>,
    pub summary: FindingSummary,
    pub witness: Option<FeasibilityWitness>,
    pub scratch_board_sha256: Option<String>,
    pub instruments: Vec<InstrumentEvidence>,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PrepareRequest {
    pub schema_version: String,
    pub screening: CorridorValidatedScreenRequest,
    pub authorities: FeasibilityAuthorities,
    pub model_requirements: Vec<ModelRequirementRow>,
    pub preflight: Vec<InstrumentEvidence>,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct FinalizeRequest {
    pub schema_version: String,
    pub prepared: FeasibilityReceipt,
    pub authorities: FeasibilityAuthorities,
    pub model_requirements: Vec<ModelRequirementRow>,
    pub screening: CorridorValidatedScreenRequest,
    pub witness_id: String,
    pub declaration_ordinal: usize,
    pub materialization_instruction: CorridorMaterializationInstruction,
    pub scratch_board_sha256: String,
    pub instruments: Vec<InstrumentEvidence>,
    pub evidence: PreRouteEvidence,
}
