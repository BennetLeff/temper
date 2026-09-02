//! The ISO7741 gate-domain qualification kernel.
//!
//! This is deliberately a pure, typed evaluator. Filesystem access, signature
//! verification and publication belong to the sealed replay runner; all
//! qualification policy (including completeness and lifecycle transitions)
//! lives here.

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};

pub const SCHEMA_VERSION: u32 = 1;
pub const ENVELOPE_DIGEST_HEX_LEN: usize = 64;

pub const REQUIRED_EVIDENCE_AXES: &[&str] = &[
    "identity.exact_parts",
    "identity.manufacturer_sources",
    "topology.domain_separation",
    "topology.channel_contract",
    "state.truth_table",
    "state.transition_matrix",
    "safety.fault_matrix",
    "uvlo.all_corner_thresholds",
    "timing.non_overlap",
    "timing.local_safe_latency",
    "power.bootstrap_startup",
    "power.gate_network_and_bias",
    "layout.isolation_corridors",
    "layout.gate_loops",
    "layout.bootstrap_loop",
    "thermal.environment_corner",
    "verification.fixture_calibration",
    "reproducibility.protected_inputs",
    "owners.internal_signoffs",
    "authority.preliminary_ruling",
    "handoff.joint_contract",
];

fn digest(value: &str) -> bool {
    value.len() == ENVELOPE_DIGEST_HEX_LEN && value.bytes().all(|b| b.is_ascii_hexdigit())
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
#[serde(rename_all = "kebab-case")]
pub enum GateDomain {
    HighSide,
    LowSide,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
#[serde(rename_all = "kebab-case")]
pub enum Command {
    Deasserted,
    Asserted,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
#[serde(rename_all = "kebab-case")]
pub enum SupplyState {
    Powered,
    Unpowered,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
#[serde(rename_all = "kebab-case")]
pub enum SupervisorState {
    BelowThreshold,
    Qualified,
    Fault,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
#[serde(rename_all = "kebab-case")]
pub enum SignalState {
    Low,
    High,
    Floating,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
#[serde(rename_all = "kebab-case")]
pub enum DefaultOutput {
    Safe,
    Unsafe,
    Unknown,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
#[serde(rename_all = "kebab-case")]
pub enum GateState {
    Safe,
    Enabled,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
#[serde(rename_all = "kebab-case")]
pub enum HealthState {
    Healthy,
    Fault,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
#[serde(rename_all = "kebab-case")]
pub enum ResetAuthority {
    ExplicitSystemReset,
    NoAutomaticReset,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
#[serde(rename_all = "kebab-case")]
pub enum EvidenceStatus {
    Pass,
    Fail,
    Pending,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
#[serde(rename_all = "kebab-case")]
pub enum TransitionScenario {
    Startup,
    SteadySwitching,
    Shutdown,
    UvloEntry,
    UvloRecovery,
    Reset,
    OneChannelLate,
    CrossChannelMismatch,
    FaultAssert,
    FaultClearWithoutReset,
}

impl TransitionScenario {
    pub const ALL: [Self; 10] = [
        Self::Startup,
        Self::SteadySwitching,
        Self::Shutdown,
        Self::UvloEntry,
        Self::UvloRecovery,
        Self::Reset,
        Self::OneChannelLate,
        Self::CrossChannelMismatch,
        Self::FaultAssert,
        Self::FaultClearWithoutReset,
    ];
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
#[serde(rename_all = "kebab-case")]
pub enum FaultKind {
    IsolatorStuckHigh,
    IsolatorStuckLow,
    ChannelMisconfiguration,
    DriverInputFault,
    DriverOutputFault,
    IsolatorSupplyOpen,
    IsolatorSupplyShort,
    DriverSupplyOpen,
    DriverSupplyShort,
    Uvlo,
    BootstrapLoss,
    GateResistorFault,
    PulldownFault,
    ThermalShutdown,
    ResetSequencing,
    CmtiDisturbance,
    CrossChannelMismatch,
}

impl FaultKind {
    pub const ALL: [Self; 17] = [
        Self::IsolatorStuckHigh,
        Self::IsolatorStuckLow,
        Self::ChannelMisconfiguration,
        Self::DriverInputFault,
        Self::DriverOutputFault,
        Self::IsolatorSupplyOpen,
        Self::IsolatorSupplyShort,
        Self::DriverSupplyOpen,
        Self::DriverSupplyShort,
        Self::Uvlo,
        Self::BootstrapLoss,
        Self::GateResistorFault,
        Self::PulldownFault,
        Self::ThermalShutdown,
        Self::ResetSequencing,
        Self::CmtiDisturbance,
        Self::CrossChannelMismatch,
    ];
}

/// The finite state-space used to generate R22 rows.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
pub struct TruthRowKey {
    pub pwm: Command,
    pub safe_state: Command,
    pub reverse_health: SignalState,
    pub isolator_supply: SupplyState,
    pub local_driver_supply: SupplyState,
    pub supervisor: SupervisorState,
    pub reset: Command,
    pub floating_input: SignalState,
    pub default_output: DefaultOutput,
}

impl TruthRowKey {
    pub fn id(self) -> String {
        format!("pwm={:?};safe={:?};health={:?};iso={:?};driver={:?};supervisor={:?};reset={:?};floating={:?};default={:?}",
            self.pwm, self.safe_state, self.reverse_health, self.isolator_supply,
            self.local_driver_supply, self.supervisor, self.reset, self.floating_input,
            self.default_output).to_lowercase()
    }

    pub fn all() -> Vec<Self> {
        let commands = [Command::Deasserted, Command::Asserted];
        let signals = [SignalState::Low, SignalState::High, SignalState::Floating];
        let supplies = [SupplyState::Powered, SupplyState::Unpowered];
        let supervisors = [
            SupervisorState::BelowThreshold,
            SupervisorState::Qualified,
            SupervisorState::Fault,
        ];
        let defaults = [
            DefaultOutput::Safe,
            DefaultOutput::Unsafe,
            DefaultOutput::Unknown,
        ];
        let mut rows = Vec::new();
        for pwm in commands {
            for safe_state in commands {
                for reverse_health in signals {
                    for isolator_supply in supplies {
                        for local_driver_supply in supplies {
                            for supervisor in supervisors {
                                for reset in commands {
                                    for floating_input in signals {
                                        for default_output in defaults {
                                            rows.push(Self {
                                                pwm,
                                                safe_state,
                                                reverse_health,
                                                isolator_supply,
                                                local_driver_supply,
                                                supervisor,
                                                reset,
                                                floating_input,
                                                default_output,
                                            });
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
        rows
    }

    fn must_be_safe(self) -> bool {
        self.safe_state == Command::Asserted
            || self.pwm == Command::Deasserted
            || self.isolator_supply == SupplyState::Unpowered
            || self.local_driver_supply == SupplyState::Unpowered
            || self.supervisor != SupervisorState::Qualified
            || self.reset == Command::Asserted
            || self.floating_input == SignalState::Floating
            || matches!(
                self.default_output,
                DefaultOutput::Unsafe | DefaultOutput::Unknown
            )
    }

    fn health_must_be_fault(self) -> bool {
        self.reverse_health != SignalState::High
            || self.isolator_supply == SupplyState::Unpowered
            || self.local_driver_supply == SupplyState::Unpowered
            || self.supervisor != SupervisorState::Qualified
            || self.floating_input == SignalState::Floating
            || matches!(
                self.default_output,
                DefaultOutput::Unsafe | DefaultOutput::Unknown
            )
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct TruthRow {
    pub key: TruthRowKey,
    pub gate: GateState,
    pub health: HealthState,
    pub detection_path: String,
    pub max_response_ns: u64,
    pub reset_authority: ResetAuthority,
    pub status: EvidenceStatus,
    pub evidence_digest: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct TransitionRow {
    pub scenario: TransitionScenario,
    pub gate: GateState,
    pub health: HealthState,
    pub detection_path: String,
    pub max_response_ns: u64,
    pub reset_authority: ResetAuthority,
    pub status: EvidenceStatus,
    pub evidence_digest: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct FaultRow {
    pub fault: FaultKind,
    pub safe_state: GateState,
    pub detection_path: String,
    pub max_response_ns: u64,
    pub latent_risk: String,
    pub reset_authority: ResetAuthority,
    pub status: EvidenceStatus,
    pub evidence_digest: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct EvidenceAxis {
    pub code: String,
    pub status: EvidenceStatus,
    pub evidence_digest: String,
    pub owner: SemanticRole,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct CandidateEnvelope {
    pub candidate_id: String,
    pub envelope_digest: String,
    pub isolator_mpn: String,
    pub local_driver_mpn: String,
    pub domains: Vec<GateDomain>,
    pub construction_projection_digest: String,
    pub allowed_transform_policy_digest: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Provenance {
    pub source_revision: String,
    pub source_sha256: String,
    pub test_conditions: String,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
#[serde(rename_all = "kebab-case")]
pub enum SemanticRole {
    BoardArchitecture,
    ElectricalPower,
    Safety,
    PcbLayout,
    MechanicalThermal,
    Sourcing,
    Verification,
}

impl SemanticRole {
    pub const ALL: [Self; 7] = [
        Self::BoardArchitecture,
        Self::ElectricalPower,
        Self::Safety,
        Self::PcbLayout,
        Self::MechanicalThermal,
        Self::Sourcing,
        Self::Verification,
    ];
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
#[serde(rename_all = "kebab-case")]
pub enum SignoffValidity {
    Valid,
    Stale,
    Superseded,
    Invalid,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct OwnerSignoff {
    pub role: SemanticRole,
    pub requirement_ids: Vec<String>,
    pub envelope_digest: String,
    pub scope_digest: String,
    pub signature_digest: String,
    pub validity: SignoffValidity,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
#[serde(rename_all = "kebab-case")]
pub enum AuthorityDisposition {
    Favorable,
    Unfavorable,
    Unresolved,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
#[serde(rename_all = "kebab-case")]
pub enum LimitationScope {
    Compatible,
    Ambiguous,
    ConstructionMutating,
    DefiniteExclusion,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct PreliminaryLimitation {
    pub id: String,
    pub scope: LimitationScope,
    pub description: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct PreliminaryRuling {
    pub envelope_digest: String,
    pub disposition: AuthorityDisposition,
    pub limitations: Vec<PreliminaryLimitation>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct GateDriveQualificationPackage {
    pub schema_version: u32,
    pub candidate: CandidateEnvelope,
    pub provenance: Provenance,
    pub evidence_axes: Vec<EvidenceAxis>,
    pub truth_rows: Vec<TruthRow>,
    pub transition_rows: Vec<TransitionRow>,
    pub fault_rows: Vec<FaultRow>,
    pub owner_signoffs: Vec<OwnerSignoff>,
    #[serde(default)]
    pub preliminary_ruling: Option<PreliminaryRuling>,
}

/// The U6 evidence index is intentionally separate from the U1-U5 evidence
/// rows above.  It is a content-addressed DAG: the runner supplies bytes for
/// each indexed object, while this module verifies every digest, scope and
/// owner disposition before deriving the internal result.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct EvidenceObject {
    pub id: String,
    pub path: String,
    pub axis: String,
    pub status: EvidenceStatus,
    pub source_revision: String,
    pub source_sha256: String,
    pub test_conditions: String,
    pub tool_identity: String,
    pub owner: String,
    pub sha256: String,
    #[serde(default)]
    pub bytes: Vec<u8>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ScopeNode {
    pub id: String,
    pub owner_role: String,
    pub requirement_ids: Vec<String>,
    pub evidence_ids: Vec<String>,
    pub scope_digest: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct InternalEvidenceAxis {
    pub code: String,
    pub status: EvidenceStatus,
    pub evidence_digest: String,
    pub owner: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct SignatureArtifact {
    pub artifact_id: String,
    pub path: String,
    pub sha256: String,
    pub signer_id: String,
    pub signer_role: String,
    pub signed_scope: String,
    pub envelope_digest: String,
    pub verification_method: String,
    pub ingestion_record: String,
    #[serde(default)]
    pub bytes: Vec<u8>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct InternalOwnerSignoff {
    pub role: String,
    pub signer_id: String,
    pub requirement_ids: Vec<String>,
    pub envelope_digest: String,
    pub scope_node_id: String,
    pub scope_digest: String,
    pub status: EvidenceStatus,
    #[serde(default)]
    pub signature_artifact: Option<SignatureArtifactRef>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct SignatureArtifactRef {
    pub artifact_id: String,
    pub path: String,
    pub sha256: String,
    pub signer_id: String,
    pub signer_role: String,
    pub signed_scope: String,
    pub envelope_digest: String,
    pub verification_method: String,
    pub ingestion_record: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct InternalEvidenceIndex {
    pub schema_version: u32,
    pub candidate: CandidateEnvelope,
    pub provenance: Provenance,
    pub evidence_axes: Vec<InternalEvidenceAxis>,
    pub evidence_objects: Vec<EvidenceObject>,
    pub evidence_root_digest: String,
    pub scope_nodes: Vec<ScopeNode>,
    pub owner_signoffs: Vec<InternalOwnerSignoff>,
    #[serde(default)]
    pub signature_artifacts: Vec<SignatureArtifact>,
}

/// Compatibility names for replay callers. They are aliases, not second
/// schemas, so there remains one Rust-owned policy surface.
pub type GateDriveManifest = GateDriveQualificationPackage;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "kebab-case")]
pub enum LifecycleStage {
    Draft,
    Rejected,
    StoppedIndeterminate,
    InternallyQualified,
    EligibleForPreliminaryExternalReview,
    ConstructionEnvelopeApproved,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum LifecycleEvent {
    InternalPass,
    InternalFail,
    InternalPending,
    SubmitForPreliminaryReview,
    PreliminaryPass,
    PreliminaryFail,
    PreliminaryPending,
}

#[derive(Debug, Clone, PartialEq, Eq, thiserror::Error)]
pub enum LifecycleError {
    #[error("illegal gate-drive lifecycle transition from {from:?} using {event:?}")]
    Illegal {
        from: LifecycleStage,
        event: LifecycleEvent,
    },
}

/// State transitions are explicit and closed. In particular this module has
/// no event which can produce a joint or production-authority result.
pub fn transition_stage(
    from: LifecycleStage,
    event: LifecycleEvent,
) -> Result<LifecycleStage, LifecycleError> {
    let next = match (from, event) {
        (LifecycleStage::Draft, LifecycleEvent::InternalPass) => {
            LifecycleStage::InternallyQualified
        }
        (LifecycleStage::Draft, LifecycleEvent::InternalFail) => LifecycleStage::Rejected,
        (LifecycleStage::Draft, LifecycleEvent::InternalPending) => {
            LifecycleStage::StoppedIndeterminate
        }
        (LifecycleStage::InternallyQualified, LifecycleEvent::InternalPass) => from,
        (LifecycleStage::InternallyQualified, LifecycleEvent::SubmitForPreliminaryReview) => {
            LifecycleStage::EligibleForPreliminaryExternalReview
        }
        (LifecycleStage::EligibleForPreliminaryExternalReview, LifecycleEvent::PreliminaryPass) => {
            LifecycleStage::ConstructionEnvelopeApproved
        }
        (LifecycleStage::EligibleForPreliminaryExternalReview, LifecycleEvent::PreliminaryFail) => {
            LifecycleStage::Rejected
        }
        (
            LifecycleStage::EligibleForPreliminaryExternalReview,
            LifecycleEvent::PreliminaryPending,
        ) => LifecycleStage::StoppedIndeterminate,
        _ => return Err(LifecycleError::Illegal { from, event }),
    };
    Ok(next)
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct GateDriveDecision {
    pub schema_version: u32,
    /// The R21 result is retained even when a later authority stage is
    /// present. This prevents an A8 receipt from being mistaken for internal
    /// evidence and makes the AE8 boundary explicit in serialized output.
    pub internal_stage: LifecycleStage,
    pub stage: LifecycleStage,
    pub candidate_id: String,
    pub envelope_digest: String,
    pub reasons: Vec<String>,
    pub limitations: Vec<PreliminaryLimitation>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct InternalDecision {
    pub schema_version: u32,
    pub candidate_id: String,
    pub envelope_digest: String,
    pub evidence_root_digest: String,
    pub internal_stage: LifecycleStage,
    pub stage: LifecycleStage,
    pub reasons: Vec<String>,
}

/// Provider-neutral packet submitted to A8.  This is deliberately separate
/// from the ruling: a provider can change without changing the construction
/// identity, and the provider's bytes never become part of the envelope.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct SubmissionOwnerReceipt {
    pub role: String,
    pub scope_digest: String,
    pub signature_artifact_digest: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct SubmissionIndex {
    pub schema_version: u32,
    pub submission_id: String,
    pub candidate_id: String,
    pub envelope_digest: String,
    pub construction_projection_digest: String,
    pub allowed_transform_policy_digest: String,
    pub fixture_digest: String,
    pub evidence_root_digest: String,
    pub internal_decision_digest: String,
    pub evidence_revision: String,
    pub standard_question: String,
    pub construction_question: String,
    pub reproduction_instructions: String,
    #[serde(default)]
    pub owner_receipts: Vec<SubmissionOwnerReceipt>,
    pub submission_digest: String,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "kebab-case")]
pub enum AuthorityResponseKind {
    Construction,
    EvidenceOnly,
    IdentityChanging,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct AuthorityReceiptArtifact {
    pub artifact_id: String,
    pub path: String,
    pub sha256: String,
    #[serde(default)]
    pub bytes: Vec<u8>,
}

/// A8's independently verifiable preliminary response.  Empty provider or
/// receipt fields are not input errors: they intentionally classify as
/// stopped-indeterminate, so an incomplete external response cannot become a
/// green result by omission.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct AuthorityRulingInput {
    pub schema_version: u32,
    pub submission_digest: String,
    pub candidate_id: String,
    pub envelope_digest: String,
    pub construction_projection_digest: String,
    pub allowed_transform_policy_digest: String,
    pub disposition: AuthorityDisposition,
    pub response_kind: AuthorityResponseKind,
    #[serde(default)]
    pub provider_id: String,
    #[serde(default)]
    pub signer_role: String,
    #[serde(default)]
    pub signed_scope_digest: String,
    #[serde(default)]
    pub verification_method: String,
    #[serde(default)]
    pub ingestion_record: String,
    #[serde(default)]
    pub receipt_artifact: Option<AuthorityReceiptArtifact>,
    #[serde(default)]
    pub limitations: Vec<PreliminaryLimitation>,
    #[serde(default)]
    pub invalidated_owner_scopes: Vec<String>,
    #[serde(default)]
    pub requested_identity_changes: Vec<String>,
    #[serde(default)]
    pub requested_construction_projection_digest: Option<String>,
    #[serde(default)]
    pub requested_allowed_transform_policy_digest: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct PreliminaryDecision {
    pub schema_version: u32,
    pub candidate_id: String,
    pub envelope_digest: String,
    pub evidence_root_digest: String,
    pub submission_digest: String,
    pub internal_stage: LifecycleStage,
    pub stage: LifecycleStage,
    pub reasons: Vec<String>,
    pub limitations: Vec<PreliminaryLimitation>,
    #[serde(default)]
    pub invalidated_owner_scopes: Vec<String>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct PreliminaryAuthorityPackage {
    #[serde(flatten)]
    pub internal: InternalEvidenceIndex,
    pub submission_index: SubmissionIndex,
    pub preliminary_ruling: AuthorityRulingInput,
}

pub type GateDriveQualificationResult = GateDriveDecision;
pub type LifecycleState = LifecycleStage;

#[derive(Debug, Clone, PartialEq, Eq, thiserror::Error)]
pub enum QualificationError {
    #[error("invalid gate-drive qualification JSON: {0}")]
    Json(String),
    #[error("unsupported gate-drive schema version {0}")]
    UnsupportedSchema(u32),
    #[error("candidate field {0} must be non-empty")]
    EmptyCandidateField(&'static str),
    #[error("candidate has invalid envelope digest")]
    InvalidEnvelopeDigest,
    #[error("candidate must be ISO7741FQDWWRQ1 and have high/low domains exactly once")]
    InvalidCandidateIdentity,
    #[error("candidate digest field {0} is invalid")]
    InvalidDigest(&'static str),
    #[error("source provenance is incomplete")]
    InvalidProvenance,
    #[error("unknown or duplicate evidence axis: {0}")]
    InvalidEvidenceAxis(String),
    #[error("missing evidence axis: {0}")]
    MissingEvidenceAxis(&'static str),
    #[error("truth table must contain exactly one row for every generated key ({0})")]
    IncompleteTruthTable(usize),
    #[error("truth row {0} contradicts the set-dominant safety invariant")]
    UnsafeTruthRow(String),
    #[error("transition matrix must contain exactly one row for every scenario ({0})")]
    IncompleteTransitions(usize),
    #[error("fault matrix must contain exactly one row for every fault ({0})")]
    IncompleteFaultMatrix(usize),
    #[error("evidence row {0} is malformed")]
    MalformedEvidence(String),
    #[error("owner sign-off coverage is invalid: {0}")]
    InvalidOwnerCoverage(String),
    #[error("preliminary ruling is invalid: {0}")]
    InvalidPreliminaryRuling(String),
    #[error("internal evidence index is invalid: {0}")]
    InvalidEvidenceIndex(String),
}

fn nonempty(value: &str) -> bool {
    !value.trim().is_empty()
}

fn validate_package(package: &GateDriveQualificationPackage) -> Result<(), QualificationError> {
    if package.schema_version != SCHEMA_VERSION {
        return Err(QualificationError::UnsupportedSchema(
            package.schema_version,
        ));
    }
    let candidate = &package.candidate;
    for (name, value) in [
        ("candidate_id", &candidate.candidate_id),
        ("isolator_mpn", &candidate.isolator_mpn),
        ("local_driver_mpn", &candidate.local_driver_mpn),
        (
            "construction_projection_digest",
            &candidate.construction_projection_digest,
        ),
        (
            "allowed_transform_policy_digest",
            &candidate.allowed_transform_policy_digest,
        ),
    ] {
        if !nonempty(value) {
            return Err(QualificationError::EmptyCandidateField(name));
        }
    }
    if !digest(&candidate.envelope_digest) {
        return Err(QualificationError::InvalidEnvelopeDigest);
    }
    if candidate.isolator_mpn != "ISO7741FQDWWRQ1"
        || candidate.local_driver_mpn != "UCC27517AQDBVRQ1"
        || candidate.domains.len() != 2
        || candidate.domains.iter().copied().collect::<BTreeSet<_>>()
            != BTreeSet::from([GateDomain::HighSide, GateDomain::LowSide])
    {
        return Err(QualificationError::InvalidCandidateIdentity);
    }
    for (name, value) in [
        (
            "construction_projection_digest",
            candidate.construction_projection_digest.as_str(),
        ),
        (
            "allowed_transform_policy_digest",
            candidate.allowed_transform_policy_digest.as_str(),
        ),
    ] {
        if !digest(value) {
            return Err(QualificationError::InvalidDigest(name));
        }
    }
    if !nonempty(&package.provenance.source_revision)
        || !digest(&package.provenance.source_sha256)
        || !nonempty(&package.provenance.test_conditions)
    {
        return Err(QualificationError::InvalidProvenance);
    }

    let mut axis_codes = BTreeSet::new();
    for axis in &package.evidence_axes {
        if !REQUIRED_EVIDENCE_AXES.contains(&axis.code.as_str())
            || !axis_codes.insert(axis.code.as_str())
            || !digest(&axis.evidence_digest)
        {
            return Err(QualificationError::InvalidEvidenceAxis(axis.code.clone()));
        }
    }
    for required in REQUIRED_EVIDENCE_AXES {
        if !axis_codes.contains(required) {
            return Err(QualificationError::MissingEvidenceAxis(required));
        }
    }

    let expected = TruthRowKey::all().into_iter().collect::<BTreeSet<_>>();
    let mut keys = BTreeSet::new();
    for row in &package.truth_rows {
        if !keys.insert(row.key) || !expected.contains(&row.key) {
            return Err(QualificationError::IncompleteTruthTable(
                package.truth_rows.len(),
            ));
        }
        if !nonempty(&row.detection_path)
            || row.max_response_ns == 0
            || !digest(&row.evidence_digest)
            || (row.key.must_be_safe() && row.gate != GateState::Safe)
            || (row.key.health_must_be_fault() && row.health != HealthState::Fault)
        {
            return Err(QualificationError::UnsafeTruthRow(row.key.id()));
        }
    }
    if keys != expected {
        return Err(QualificationError::IncompleteTruthTable(expected.len()));
    }

    let mut transitions = BTreeSet::new();
    for row in &package.transition_rows {
        if !transitions.insert(row.scenario)
            || !nonempty(&row.detection_path)
            || row.max_response_ns == 0
            || !digest(&row.evidence_digest)
        {
            return Err(QualificationError::MalformedEvidence(
                "transition".to_owned(),
            ));
        }
        if row.scenario == TransitionScenario::FaultClearWithoutReset && row.gate != GateState::Safe
        {
            return Err(QualificationError::UnsafeTruthRow(
                "fault-clear-without-reset".to_owned(),
            ));
        }
    }
    if transitions.len() != TransitionScenario::ALL.len()
        || TransitionScenario::ALL
            .iter()
            .any(|scenario| !transitions.contains(scenario))
    {
        return Err(QualificationError::IncompleteTransitions(
            TransitionScenario::ALL.len(),
        ));
    }

    let mut faults = BTreeSet::new();
    for row in &package.fault_rows {
        if !faults.insert(row.fault)
            || row.safe_state != GateState::Safe
            || !nonempty(&row.detection_path)
            || !nonempty(&row.latent_risk)
            || row.max_response_ns == 0
            || !digest(&row.evidence_digest)
        {
            return Err(QualificationError::MalformedEvidence("fault".to_owned()));
        }
    }
    if faults.len() != FaultKind::ALL.len()
        || FaultKind::ALL.iter().any(|fault| !faults.contains(fault))
    {
        return Err(QualificationError::IncompleteFaultMatrix(
            FaultKind::ALL.len(),
        ));
    }

    let mut roles = BTreeMap::new();
    let mut covered_requirements = BTreeSet::new();
    for signoff in &package.owner_signoffs {
        if roles.insert(signoff.role, signoff).is_some() {
            return Err(QualificationError::InvalidOwnerCoverage(
                "duplicate semantic role".to_owned(),
            ));
        }
        if signoff.validity != SignoffValidity::Valid
            || signoff.envelope_digest != candidate.envelope_digest
            || !digest(&signoff.scope_digest)
            || !digest(&signoff.signature_digest)
            || signoff.requirement_ids.is_empty()
            || signoff.requirement_ids.iter().any(|id| !nonempty(id))
        {
            return Err(QualificationError::InvalidOwnerCoverage(format!(
                "{:?}",
                signoff.role
            )));
        }
        for requirement in &signoff.requirement_ids {
            if !matches!(
                requirement.as_str(),
                "R1" | "R2"
                    | "R3"
                    | "R4"
                    | "R5"
                    | "R6"
                    | "R7"
                    | "R8"
                    | "R9"
                    | "R10"
                    | "R11"
                    | "R12"
                    | "R13"
                    | "R14"
                    | "R15"
                    | "R16"
                    | "R17"
                    | "R18"
                    | "R19"
                    | "R20"
                    | "R21"
                    | "R22"
                    | "R23"
            ) {
                return Err(QualificationError::InvalidOwnerCoverage(format!(
                    "unknown requirement {requirement}"
                )));
            }
            covered_requirements.insert(requirement.as_str());
        }
    }
    if SemanticRole::ALL
        .iter()
        .any(|role| !roles.contains_key(role))
    {
        return Err(QualificationError::InvalidOwnerCoverage(
            "missing semantic role".to_owned(),
        ));
    }
    if (1..=23).any(|id| !covered_requirements.contains(format!("R{id}").as_str())) {
        return Err(QualificationError::InvalidOwnerCoverage(
            "missing internal requirement coverage".to_owned(),
        ));
    }

    if let Some(ruling) = &package.preliminary_ruling {
        if ruling.envelope_digest != candidate.envelope_digest {
            return Err(QualificationError::InvalidPreliminaryRuling(
                "envelope digest mismatch".to_owned(),
            ));
        }
        for limitation in &ruling.limitations {
            if !nonempty(&limitation.id) || !nonempty(&limitation.description) {
                return Err(QualificationError::InvalidPreliminaryRuling(
                    "limitation is incomplete".to_owned(),
                ));
            }
        }
    }
    Ok(())
}

/// Derive the only legal internal/preliminary lifecycle states. Fail always
/// wins over pending; no authority receipt can turn incomplete evidence green.
pub fn evaluate_gate_drive(
    package: &GateDriveQualificationPackage,
) -> Result<GateDriveDecision, QualificationError> {
    validate_package(package)?;
    let mut failures = Vec::new();
    let mut pending = Vec::new();
    for axis in &package.evidence_axes {
        // These are downstream handoff axes. Their absence/pending state must
        // not prevent the R21 internal result (AE8); the preliminary receipt
        // itself is the authority gate for the later stage.
        if matches!(
            axis.code.as_str(),
            "authority.preliminary_ruling" | "handoff.joint_contract"
        ) {
            continue;
        }
        match axis.status {
            EvidenceStatus::Fail => failures.push(axis.code.clone()),
            EvidenceStatus::Pending => pending.push(axis.code.clone()),
            EvidenceStatus::Pass => {}
        }
    }
    for row in &package.truth_rows {
        match row.status {
            EvidenceStatus::Fail => failures.push(format!("truth:{}", row.key.id())),
            EvidenceStatus::Pending => pending.push(format!("truth:{}", row.key.id())),
            EvidenceStatus::Pass => {}
        }
    }
    for row in &package.transition_rows {
        match row.status {
            EvidenceStatus::Fail => failures.push(format!("transition:{:?}", row.scenario)),
            EvidenceStatus::Pending => pending.push(format!("transition:{:?}", row.scenario)),
            EvidenceStatus::Pass => {}
        }
    }
    for row in &package.fault_rows {
        match row.status {
            EvidenceStatus::Fail => failures.push(format!("fault:{:?}", row.fault)),
            EvidenceStatus::Pending => pending.push(format!("fault:{:?}", row.fault)),
            EvidenceStatus::Pass => {}
        }
    }
    failures.sort();
    pending.sort();
    let has_failures = !failures.is_empty();
    let has_pending = !pending.is_empty();
    let (stage, mut reasons, limitations) = if has_failures {
        (LifecycleStage::Rejected, failures.clone(), Vec::new())
    } else if has_pending {
        (
            LifecycleStage::StoppedIndeterminate,
            pending.clone(),
            Vec::new(),
        )
    } else if let Some(ruling) = &package.preliminary_ruling {
        match ruling.disposition {
            AuthorityDisposition::Unfavorable => (
                LifecycleStage::Rejected,
                vec!["authority.preliminary_ruling".to_owned()],
                Vec::new(),
            ),
            AuthorityDisposition::Unresolved => (
                LifecycleStage::StoppedIndeterminate,
                vec!["authority.preliminary_ruling".to_owned()],
                Vec::new(),
            ),
            AuthorityDisposition::Favorable => {
                let incompatible = ruling.limitations.iter().any(|limitation| {
                    matches!(
                        limitation.scope,
                        LimitationScope::Ambiguous
                            | LimitationScope::ConstructionMutating
                            | LimitationScope::DefiniteExclusion
                    )
                });
                if incompatible {
                    let hard = ruling.limitations.iter().any(|limitation| {
                        matches!(
                            limitation.scope,
                            LimitationScope::ConstructionMutating
                                | LimitationScope::DefiniteExclusion
                        )
                    });
                    (
                        if hard {
                            LifecycleStage::Rejected
                        } else {
                            LifecycleStage::StoppedIndeterminate
                        },
                        vec!["authority.limitation".to_owned()],
                        Vec::new(),
                    )
                } else {
                    (
                        LifecycleStage::ConstructionEnvelopeApproved,
                        Vec::new(),
                        ruling.limitations.clone(),
                    )
                }
            }
        }
    } else {
        (
            LifecycleStage::EligibleForPreliminaryExternalReview,
            Vec::new(),
            Vec::new(),
        )
    };
    let internal_stage = if has_failures {
        LifecycleStage::Rejected
    } else if has_pending {
        LifecycleStage::StoppedIndeterminate
    } else {
        LifecycleStage::InternallyQualified
    };
    reasons.sort();
    Ok(GateDriveDecision {
        schema_version: package.schema_version,
        internal_stage,
        stage,
        candidate_id: package.candidate.candidate_id.clone(),
        envelope_digest: package.candidate.envelope_digest.clone(),
        reasons,
        limitations,
    })
}

pub fn evaluate_gate_drive_json(input: &str) -> Result<String, QualificationError> {
    if let Ok(value) = serde_json::from_str::<serde_json::Value>(input) {
        if value.get("submission_index").is_some() && value.get("preliminary_ruling").is_some() {
            return evaluate_preliminary_authority_json(input);
        }
        if value.get("evidence_objects").is_some() {
            return evaluate_internal_index_json(input);
        }
    }
    let package: GateDriveQualificationPackage =
        serde_json::from_str(input).map_err(|error| QualificationError::Json(error.to_string()))?;
    let decision = evaluate_gate_drive(&package)?;
    serde_json::to_string_pretty(&decision)
        .map_err(|error| QualificationError::Json(error.to_string()))
}

pub fn evaluate_manifest(
    package: &GateDriveManifest,
) -> Result<GateDriveQualificationResult, QualificationError> {
    evaluate_gate_drive(package)
}

pub fn evaluate_manifest_json(input: &str) -> Result<String, QualificationError> {
    evaluate_gate_drive_json(input)
}

const INTERNAL_ROLES: &[&str] = &[
    "iso.board_architecture",
    "iso.electrical_power",
    "iso.safety",
    "iso.pcb_layout",
    "iso.mechanical_thermal",
    "iso.sourcing",
    "iso.verification",
];

const INTERNAL_AXES: &[&str] = &[
    "identity.exact_parts",
    "identity.manufacturer_sources",
    "topology.domain_separation",
    "topology.channel_contract",
    "state.truth_table",
    "state.transition_matrix",
    "safety.fault_matrix",
    "uvlo.all_corner_thresholds",
    "timing.non_overlap",
    "timing.local_safe_latency",
    "power.bootstrap_startup",
    "power.gate_network_and_bias",
    "layout.isolation_corridors",
    "layout.gate_loops",
    "layout.bootstrap_loop",
    "thermal.environment_corner",
    "verification.fixture_calibration",
    "reproducibility.protected_inputs",
    "owners.internal_signoffs",
    "authority.preliminary_ruling",
    "handoff.joint_contract",
];

fn sha256_hex(bytes: &[u8]) -> String {
    let mut hasher = Sha256::new();
    hasher.update(bytes);
    hasher
        .finalize()
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

fn digest_lines(lines: impl IntoIterator<Item = String>) -> String {
    let mut bytes = Vec::new();
    for line in lines {
        bytes.extend_from_slice(line.as_bytes());
        bytes.push(0);
    }
    sha256_hex(&bytes)
}

fn internal_scope_digest(node: &ScopeNode, objects: &BTreeMap<&str, &EvidenceObject>) -> String {
    let mut evidence = node
        .evidence_ids
        .iter()
        .filter_map(|id| {
            objects
                .get(id.as_str())
                .map(|object| (id, object.sha256.as_str()))
        })
        .collect::<Vec<_>>();
    evidence.sort_by(|left, right| left.0.cmp(right.0));
    let mut lines = vec![node.owner_role.clone()];
    lines.extend(node.requirement_ids.iter().cloned());
    lines.extend(
        evidence
            .into_iter()
            .flat_map(|(id, sha)| [id.clone(), sha.to_owned()]),
    );
    digest_lines(lines)
}

fn owner_allows_requirement(role: &str, requirement: &str) -> bool {
    match role {
        "iso.board_architecture" => {
            matches!(requirement, "R1" | "R2" | "R3" | "R4" | "R19" | "R21")
        }
        "iso.electrical_power" => matches!(
            requirement,
            "R1" | "R2"
                | "R3"
                | "R4"
                | "R6"
                | "R7"
                | "R8"
                | "R9"
                | "R10"
                | "R11"
                | "R12"
                | "R14"
                | "R15"
                | "R16"
                | "R17"
                | "R22"
                | "R23"
        ),
        "iso.safety" => matches!(requirement, "R3" | "R10" | "R11" | "R12" | "R22" | "R23"),
        "iso.pcb_layout" => matches!(requirement, "R5" | "R13" | "R14" | "R15" | "R16"),
        "iso.mechanical_thermal" => matches!(requirement, "R5" | "R13" | "R17"),
        "iso.sourcing" => requirement == "R5",
        "iso.verification" => matches!(requirement, "R18" | "R20" | "R21" | "R22" | "R23"),
        _ => false,
    }
}

type ValidatedInternalIndex<'a> = (
    BTreeMap<&'a str, &'a EvidenceObject>,
    BTreeMap<&'a str, &'a SignatureArtifact>,
);

fn validate_internal_index(
    package: &InternalEvidenceIndex,
) -> Result<ValidatedInternalIndex<'_>, QualificationError> {
    if package.schema_version != SCHEMA_VERSION {
        return Err(QualificationError::UnsupportedSchema(
            package.schema_version,
        ));
    }
    let candidate = &package.candidate;
    if !digest(&candidate.envelope_digest)
        || !digest(&candidate.construction_projection_digest)
        || !digest(&candidate.allowed_transform_policy_digest)
        || candidate.candidate_id.trim().is_empty()
        || candidate.isolator_mpn != "ISO7741FQDWWRQ1"
        || candidate.local_driver_mpn != "UCC27517AQDBVRQ1"
        || candidate.domains.iter().copied().collect::<BTreeSet<_>>()
            != BTreeSet::from([GateDomain::HighSide, GateDomain::LowSide])
    {
        return Err(QualificationError::InvalidEvidenceIndex(
            "candidate identity is incomplete".to_owned(),
        ));
    }
    if !nonempty(&package.provenance.source_revision)
        || !digest(&package.provenance.source_sha256)
        || !nonempty(&package.provenance.test_conditions)
    {
        return Err(QualificationError::InvalidEvidenceIndex(
            "provenance is incomplete".to_owned(),
        ));
    }

    let mut objects = BTreeMap::new();
    for object in &package.evidence_objects {
        if object.id.trim().is_empty()
            || object.path.trim().is_empty()
            || object.axis.trim().is_empty()
            || object.source_revision.trim().is_empty()
            || object.test_conditions.trim().is_empty()
            || object.tool_identity.trim().is_empty()
            || object.owner.trim().is_empty()
            || !digest(&object.sha256)
            || !digest(&object.source_sha256)
            || objects.insert(object.id.as_str(), object).is_some()
        {
            return Err(QualificationError::InvalidEvidenceIndex(format!(
                "invalid or duplicate evidence object {}",
                object.id
            )));
        }
        if sha256_hex(&object.bytes) != object.sha256.to_ascii_lowercase() {
            return Err(QualificationError::InvalidEvidenceIndex(format!(
                "evidence object digest mismatch {}",
                object.id
            )));
        }
    }
    if objects.is_empty() {
        return Err(QualificationError::InvalidEvidenceIndex(
            "evidence_objects is empty".to_owned(),
        ));
    }
    let root = digest_lines(
        objects
            .iter()
            .flat_map(|(id, object)| [(*id).to_owned(), object.sha256.clone()]),
    );
    if root != package.evidence_root_digest.to_ascii_lowercase() {
        return Err(QualificationError::InvalidEvidenceIndex(
            "evidence root digest mismatch".to_owned(),
        ));
    }

    let mut axes = BTreeMap::new();
    for axis in &package.evidence_axes {
        if !INTERNAL_AXES.contains(&axis.code.as_str())
            || axes.insert(axis.code.as_str(), axis).is_some()
            || !digest(&axis.evidence_digest)
            || !objects
                .values()
                .any(|object| object.sha256 == axis.evidence_digest)
        {
            return Err(QualificationError::InvalidEvidenceIndex(format!(
                "invalid or duplicate evidence axis {}",
                axis.code
            )));
        }
    }
    if axes.len() != INTERNAL_AXES.len() {
        return Err(QualificationError::InvalidEvidenceIndex(
            "missing required evidence axis".to_owned(),
        ));
    }

    let mut scopes = BTreeMap::new();
    for node in &package.scope_nodes {
        if node.id.trim().is_empty()
            || !INTERNAL_ROLES.contains(&node.owner_role.as_str())
            || !digest(&node.scope_digest)
            || node.requirement_ids.is_empty()
            || node.evidence_ids.is_empty()
            || node
                .evidence_ids
                .iter()
                .any(|id| !objects.contains_key(id.as_str()))
            || scopes.insert(node.id.as_str(), node).is_some()
        {
            return Err(QualificationError::InvalidEvidenceIndex(format!(
                "invalid or duplicate scope node {}",
                node.id
            )));
        }
        if internal_scope_digest(node, &objects) != node.scope_digest.to_ascii_lowercase() {
            return Err(QualificationError::InvalidEvidenceIndex(format!(
                "scope digest mismatch {}",
                node.id
            )));
        }
    }
    if scopes.len() != INTERNAL_ROLES.len() {
        return Err(QualificationError::InvalidEvidenceIndex(
            "exactly one scope node per internal role is required".to_owned(),
        ));
    }

    let mut signatures = BTreeMap::new();
    for signature in &package.signature_artifacts {
        if signature.artifact_id.trim().is_empty()
            || !digest(&signature.sha256)
            || signature.path.trim().is_empty()
            || signature.signer_id.trim().is_empty()
            || !INTERNAL_ROLES.contains(&signature.signer_role.as_str())
            || !digest(&signature.signed_scope)
            || !digest(&signature.envelope_digest)
            || signature.verification_method.trim().is_empty()
            || signature.ingestion_record.trim().is_empty()
            || signatures
                .insert(signature.artifact_id.as_str(), signature)
                .is_some()
        {
            return Err(QualificationError::InvalidEvidenceIndex(
                "invalid or duplicate signature artifact".to_owned(),
            ));
        }
        if sha256_hex(&signature.bytes) != signature.sha256.to_ascii_lowercase() {
            return Err(QualificationError::InvalidEvidenceIndex(
                "signature artifact digest mismatch".to_owned(),
            ));
        }
    }

    let mut signoffs = BTreeMap::new();
    let mut covered = BTreeSet::new();
    for signoff in &package.owner_signoffs {
        if !INTERNAL_ROLES.contains(&signoff.role.as_str())
            || signoff.signer_id.trim().is_empty()
            || !digest(&signoff.envelope_digest)
            || signoff.envelope_digest != candidate.envelope_digest
            || !digest(&signoff.scope_digest)
            || scopes
                .get(signoff.scope_node_id.as_str())
                .map(|node| node.scope_digest.as_str())
                != Some(signoff.scope_digest.as_str())
            || signoff.requirement_ids.is_empty()
            || signoff.requirement_ids.iter().any(|id| {
                !matches!(
                    id.as_str(),
                    "R1" | "R2"
                        | "R3"
                        | "R4"
                        | "R5"
                        | "R6"
                        | "R7"
                        | "R8"
                        | "R9"
                        | "R10"
                        | "R11"
                        | "R12"
                        | "R13"
                        | "R14"
                        | "R15"
                        | "R16"
                        | "R17"
                        | "R18"
                        | "R19"
                        | "R20"
                        | "R21"
                        | "R22"
                        | "R23"
                )
            })
            || signoffs.insert(signoff.role.as_str(), signoff).is_some()
        {
            return Err(QualificationError::InvalidEvidenceIndex(
                "invalid or duplicate owner sign-off".to_owned(),
            ));
        }
        covered.extend(signoff.requirement_ids.iter().map(String::as_str));
        if let Some(node) = scopes.get(signoff.scope_node_id.as_str()) {
            if node.owner_role != signoff.role {
                return Err(QualificationError::InvalidEvidenceIndex(
                    "owner sign-off role does not match scope owner_role".to_owned(),
                ));
            }
            if signoff
                .requirement_ids
                .iter()
                .any(|requirement| !node.requirement_ids.contains(requirement))
            {
                return Err(QualificationError::InvalidEvidenceIndex(
                    "owner sign-off exceeds its scope node".to_owned(),
                ));
            }
        }
        if signoff
            .requirement_ids
            .iter()
            .any(|requirement| !owner_allows_requirement(&signoff.role, requirement))
        {
            return Err(QualificationError::InvalidEvidenceIndex(
                "owner sign-off contains a wrong-owner requirement".to_owned(),
            ));
        }
        match (&signoff.status, &signoff.signature_artifact) {
            (EvidenceStatus::Pass, Some(reference)) => {
                let artifact = signatures
                    .get(reference.artifact_id.as_str())
                    .ok_or_else(|| {
                        QualificationError::InvalidEvidenceIndex(
                            "owner signature artifact is absent".to_owned(),
                        )
                    })?;
                if reference.path != artifact.path
                    || reference.sha256 != artifact.sha256
                    || reference.signer_id != artifact.signer_id
                    || reference.signer_role != artifact.signer_role
                    || reference.signed_scope != artifact.signed_scope
                    || reference.envelope_digest != artifact.envelope_digest
                {
                    return Err(QualificationError::InvalidEvidenceIndex(
                        "owner signature metadata does not match artifact".to_owned(),
                    ));
                }
                if reference.signer_id != signoff.signer_id
                    || reference.signer_role != signoff.role
                    || reference.signed_scope != signoff.scope_digest
                    || reference.envelope_digest != signoff.envelope_digest
                {
                    return Err(QualificationError::InvalidEvidenceIndex(
                        "owner sign-off metadata does not match its scope and signer".to_owned(),
                    ));
                }
            }
            (EvidenceStatus::Pending, None) => {}
            (_, _) => {
                return Err(QualificationError::InvalidEvidenceIndex(
                    "pass/fail sign-offs require an immutable signature artifact".to_owned(),
                ));
            }
        }
    }
    if signoffs.len() != INTERNAL_ROLES.len() || covered.len() != 23 {
        return Err(QualificationError::InvalidEvidenceIndex(
            "A1-A7 sign-off coverage is incomplete".to_owned(),
        ));
    }
    Ok((objects, signatures))
}

pub fn evaluate_internal_index(
    package: &InternalEvidenceIndex,
) -> Result<InternalDecision, QualificationError> {
    let _ = validate_internal_index(package)?;
    let mut failures = Vec::new();
    let mut pending = Vec::new();
    for axis in &package.evidence_axes {
        if matches!(
            axis.code.as_str(),
            "authority.preliminary_ruling" | "handoff.joint_contract"
        ) {
            continue;
        }
        match axis.status {
            EvidenceStatus::Fail => failures.push(axis.code.clone()),
            EvidenceStatus::Pending => pending.push(axis.code.clone()),
            EvidenceStatus::Pass => {}
        }
    }
    for signoff in &package.owner_signoffs {
        match signoff.status {
            EvidenceStatus::Fail => failures.push(format!("owner:{}", signoff.role)),
            EvidenceStatus::Pending => pending.push(format!("owner:{}", signoff.role)),
            EvidenceStatus::Pass => {}
        }
    }
    failures.sort();
    pending.sort();
    let internal_stage = if !failures.is_empty() {
        LifecycleStage::Rejected
    } else if !pending.is_empty() {
        LifecycleStage::StoppedIndeterminate
    } else {
        LifecycleStage::InternallyQualified
    };
    let mut reasons = if !failures.is_empty() {
        failures
    } else {
        pending
    };
    reasons.sort();
    Ok(InternalDecision {
        schema_version: package.schema_version,
        candidate_id: package.candidate.candidate_id.clone(),
        envelope_digest: package.candidate.envelope_digest.clone(),
        evidence_root_digest: package.evidence_root_digest.clone(),
        internal_stage,
        stage: internal_stage,
        reasons,
    })
}

pub fn evaluate_internal_index_json(input: &str) -> Result<String, QualificationError> {
    let package: InternalEvidenceIndex =
        serde_json::from_str(input).map_err(|error| QualificationError::Json(error.to_string()))?;
    let decision = evaluate_internal_index(&package)?;
    serde_json::to_string_pretty(&decision)
        .map_err(|error| QualificationError::Json(error.to_string()))
}

fn valid_submission(index: &SubmissionIndex) -> bool {
    index.schema_version == SCHEMA_VERSION
        && nonempty(&index.submission_id)
        && nonempty(&index.candidate_id)
        && digest(&index.envelope_digest)
        && digest(&index.construction_projection_digest)
        && digest(&index.allowed_transform_policy_digest)
        && digest(&index.fixture_digest)
        && digest(&index.evidence_root_digest)
        && digest(&index.internal_decision_digest)
        && nonempty(&index.evidence_revision)
        && nonempty(&index.standard_question)
        && nonempty(&index.construction_question)
        && nonempty(&index.reproduction_instructions)
        && digest(&index.submission_digest)
        && index.owner_receipts.iter().all(|receipt| {
            INTERNAL_ROLES.contains(&receipt.role.as_str())
                && digest(&receipt.scope_digest)
                && digest(&receipt.signature_artifact_digest)
        })
}

fn submission_content_digest(index: &SubmissionIndex) -> String {
    let mut lines = vec![
        index.schema_version.to_string(),
        index.submission_id.clone(),
        index.candidate_id.clone(),
        index.envelope_digest.clone(),
        index.construction_projection_digest.clone(),
        index.allowed_transform_policy_digest.clone(),
        index.fixture_digest.clone(),
        index.evidence_root_digest.clone(),
        index.internal_decision_digest.clone(),
        index.evidence_revision.clone(),
        index.standard_question.clone(),
        index.construction_question.clone(),
        index.reproduction_instructions.clone(),
    ];
    let mut receipts = index.owner_receipts.iter().collect::<Vec<_>>();
    receipts.sort_by(|left, right| left.role.cmp(&right.role));
    for receipt in receipts {
        lines.extend([
            receipt.role.clone(),
            receipt.scope_digest.clone(),
            receipt.signature_artifact_digest.clone(),
        ]);
    }
    digest_lines(lines)
}

fn material_digest(value: &str) -> bool {
    digest(value) && value.bytes().any(|byte| byte != b'0')
}

fn authority_receipt_available(ruling: &AuthorityRulingInput) -> bool {
    if ruling.provider_id.trim().is_empty()
        || ruling.signer_role != "iso.external_compliance"
        || ruling.signed_scope_digest != ruling.submission_digest
        || !digest(&ruling.signed_scope_digest)
        || ruling.verification_method.trim().is_empty()
        || ruling.ingestion_record.trim().is_empty()
    {
        return false;
    }
    let Some(artifact) = &ruling.receipt_artifact else {
        return false;
    };
    !artifact.artifact_id.trim().is_empty()
        && !artifact.path.trim().is_empty()
        && digest(&artifact.sha256)
        && !artifact.bytes.is_empty()
        && sha256_hex(&artifact.bytes) == artifact.sha256.to_ascii_lowercase()
}

fn validate_preliminary_input(
    package: &PreliminaryAuthorityPackage,
) -> Result<(), QualificationError> {
    if package.submission_index.schema_version != SCHEMA_VERSION
        || package.preliminary_ruling.schema_version != SCHEMA_VERSION
    {
        return Err(QualificationError::InvalidPreliminaryRuling(
            "unsupported preliminary schema version".to_owned(),
        ));
    }
    if !valid_submission(&package.submission_index) {
        return Err(QualificationError::InvalidPreliminaryRuling(
            "submission index required field is invalid".to_owned(),
        ));
    }
    let ruling = &package.preliminary_ruling;
    let mut limitation_ids = BTreeSet::new();
    for limitation in &ruling.limitations {
        if !nonempty(&limitation.id)
            || !nonempty(&limitation.description)
            || !limitation_ids.insert(limitation.id.as_str())
        {
            return Err(QualificationError::InvalidPreliminaryRuling(
                "limitation is empty or duplicated".to_owned(),
            ));
        }
    }
    if ruling
        .invalidated_owner_scopes
        .iter()
        .any(|scope| scope.trim().is_empty() || !INTERNAL_ROLES.contains(&scope.as_str()))
    {
        return Err(QualificationError::InvalidPreliminaryRuling(
            "invalidated owner scope is not an ISO semantic role".to_owned(),
        ));
    }
    Ok(())
}

/// Evaluate U7's preliminary authority packet.  This intentionally retains
/// the U6 internal result and cannot emit either a joint or production state.
pub fn evaluate_preliminary_authority(
    package: &PreliminaryAuthorityPackage,
) -> Result<PreliminaryDecision, QualificationError> {
    validate_preliminary_input(package)?;
    let internal = evaluate_internal_index(&package.internal)?;
    let submission = &package.submission_index;
    let ruling = &package.preliminary_ruling;

    // Internal rejection/pending is authoritative.  In particular, a
    // favorable-looking placeholder can never launder the current rejected
    // U6 result into an A8 approval.
    if internal.internal_stage != LifecycleStage::InternallyQualified {
        return Ok(PreliminaryDecision {
            schema_version: package.internal.schema_version,
            candidate_id: internal.candidate_id,
            envelope_digest: internal.envelope_digest,
            evidence_root_digest: internal.evidence_root_digest,
            submission_digest: submission.submission_digest.clone(),
            internal_stage: internal.internal_stage,
            stage: internal.internal_stage,
            reasons: internal.reasons,
            limitations: Vec::new(),
            invalidated_owner_scopes: Vec::new(),
        });
    }

    if [
        submission.envelope_digest.as_str(),
        submission.construction_projection_digest.as_str(),
        submission.allowed_transform_policy_digest.as_str(),
        submission.fixture_digest.as_str(),
        submission.evidence_root_digest.as_str(),
        submission.internal_decision_digest.as_str(),
        submission.submission_digest.as_str(),
    ]
    .iter()
    .any(|value| !material_digest(value))
    {
        return Ok(PreliminaryDecision {
            schema_version: package.internal.schema_version,
            candidate_id: internal.candidate_id,
            envelope_digest: internal.envelope_digest,
            evidence_root_digest: internal.evidence_root_digest,
            submission_digest: submission.submission_digest.clone(),
            internal_stage: internal.internal_stage,
            stage: LifecycleStage::StoppedIndeterminate,
            reasons: vec!["authority.submission-unfrozen".to_owned()],
            limitations: Vec::new(),
            invalidated_owner_scopes: Vec::new(),
        });
    }

    if submission.submission_digest != submission_content_digest(submission) {
        return Ok(PreliminaryDecision {
            schema_version: package.internal.schema_version,
            candidate_id: internal.candidate_id,
            envelope_digest: internal.envelope_digest,
            evidence_root_digest: internal.evidence_root_digest,
            submission_digest: submission.submission_digest.clone(),
            internal_stage: internal.internal_stage,
            stage: LifecycleStage::StoppedIndeterminate,
            reasons: vec!["authority.submission-digest-mismatch".to_owned()],
            limitations: Vec::new(),
            invalidated_owner_scopes: Vec::new(),
        });
    }

    if ruling.candidate_id != package.internal.candidate.candidate_id
        || ruling.submission_digest != submission.submission_digest
        || ruling.envelope_digest != submission.envelope_digest
        || ruling.construction_projection_digest != submission.construction_projection_digest
        || ruling.allowed_transform_policy_digest != submission.allowed_transform_policy_digest
        || submission.candidate_id != package.internal.candidate.candidate_id
        || submission.envelope_digest != package.internal.candidate.envelope_digest
        || submission.construction_projection_digest
            != package.internal.candidate.construction_projection_digest
        || submission.allowed_transform_policy_digest
            != package.internal.candidate.allowed_transform_policy_digest
    {
        return Ok(PreliminaryDecision {
            schema_version: package.internal.schema_version,
            candidate_id: internal.candidate_id,
            envelope_digest: internal.envelope_digest,
            evidence_root_digest: internal.evidence_root_digest,
            submission_digest: submission.submission_digest.clone(),
            internal_stage: internal.internal_stage,
            stage: LifecycleStage::StoppedIndeterminate,
            reasons: vec!["authority.identity-mismatch".to_owned()],
            limitations: Vec::new(),
            invalidated_owner_scopes: Vec::new(),
        });
    }

    let receipt_unavailable = !authority_receipt_available(ruling);
    let mut reasons = Vec::new();
    if receipt_unavailable {
        reasons.push("authority.receipt-unverifiable".to_owned());
    }
    let requested_projection = ruling
        .requested_construction_projection_digest
        .as_deref()
        .is_some_and(|value| value != submission.construction_projection_digest);
    let requested_policy = ruling
        .requested_allowed_transform_policy_digest
        .as_deref()
        .is_some_and(|value| value != submission.allowed_transform_policy_digest);
    let identity_changing = matches!(
        ruling.response_kind,
        AuthorityResponseKind::IdentityChanging
    ) || !ruling.requested_identity_changes.is_empty()
        || requested_projection
        || requested_policy;
    if identity_changing {
        reasons.push("authority.identity-changing-request".to_owned());
    }

    let mut invalidated = ruling.invalidated_owner_scopes.clone();
    invalidated.sort();
    invalidated.dedup();
    let evidence_only = matches!(ruling.response_kind, AuthorityResponseKind::EvidenceOnly);
    let missing_evidence_scope = evidence_only && invalidated.is_empty();
    if evidence_only
        && !missing_evidence_scope
        && !invalidated.iter().any(|role| role == "iso.verification")
    {
        invalidated.push("iso.verification".to_owned());
        invalidated.sort();
    }
    let mut limitations = ruling.limitations.clone();
    limitations.sort_by(|left, right| left.id.cmp(&right.id));

    let stage = if identity_changing && !receipt_unavailable {
        LifecycleStage::Rejected
    } else if !reasons.is_empty() {
        LifecycleStage::StoppedIndeterminate
    } else if evidence_only {
        if missing_evidence_scope {
            reasons.push("authority.evidence-only.missing-scopes".to_owned());
        }
        LifecycleStage::StoppedIndeterminate
    } else {
        match ruling.disposition {
            AuthorityDisposition::Unfavorable => LifecycleStage::Rejected,
            AuthorityDisposition::Unresolved => LifecycleStage::StoppedIndeterminate,
            AuthorityDisposition::Favorable => {
                let definite = limitations.iter().any(|limitation| {
                    matches!(
                        limitation.scope,
                        LimitationScope::ConstructionMutating | LimitationScope::DefiniteExclusion
                    )
                });
                let ambiguous = limitations
                    .iter()
                    .any(|limitation| matches!(limitation.scope, LimitationScope::Ambiguous));
                if definite {
                    LifecycleStage::Rejected
                } else if ambiguous {
                    LifecycleStage::StoppedIndeterminate
                } else {
                    LifecycleStage::ConstructionEnvelopeApproved
                }
            }
        }
    };
    if !reasons.is_empty() {
        reasons.sort();
    }
    if matches!(ruling.disposition, AuthorityDisposition::Unfavorable) {
        reasons.push("authority.preliminary_ruling".to_owned());
    }
    reasons.sort();
    Ok(PreliminaryDecision {
        schema_version: package.internal.schema_version,
        candidate_id: internal.candidate_id,
        envelope_digest: internal.envelope_digest,
        evidence_root_digest: internal.evidence_root_digest,
        submission_digest: submission.submission_digest.clone(),
        internal_stage: internal.internal_stage,
        stage,
        reasons,
        limitations: if stage == LifecycleStage::ConstructionEnvelopeApproved {
            limitations
        } else {
            Vec::new()
        },
        invalidated_owner_scopes: invalidated,
    })
}

pub fn evaluate_preliminary_authority_json(input: &str) -> Result<String, QualificationError> {
    let package: PreliminaryAuthorityPackage =
        serde_json::from_str(input).map_err(|error| QualificationError::Json(error.to_string()))?;
    let decision = evaluate_preliminary_authority(&package)?;
    serde_json::to_string_pretty(&decision)
        .map_err(|error| QualificationError::Json(error.to_string()))
}

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

    fn valid_package() -> GateDriveQualificationPackage {
        let envelope_digest = "a".repeat(64);
        let evidence_digest = "b".repeat(64);
        let candidate = CandidateEnvelope {
            candidate_id: "iso7741-baseline".to_owned(),
            envelope_digest: envelope_digest.clone(),
            isolator_mpn: "ISO7741FQDWWRQ1".to_owned(),
            local_driver_mpn: "UCC27517AQDBVRQ1".to_owned(),
            domains: vec![GateDomain::HighSide, GateDomain::LowSide],
            construction_projection_digest: "c".repeat(64),
            allowed_transform_policy_digest: "d".repeat(64),
        };
        let evidence_axes = REQUIRED_EVIDENCE_AXES
            .iter()
            .map(|code| EvidenceAxis {
                code: (*code).to_owned(),
                status: EvidenceStatus::Pass,
                evidence_digest: evidence_digest.clone(),
                owner: SemanticRole::Verification,
            })
            .collect();
        let truth_rows = TruthRowKey::all()
            .into_iter()
            .map(|key| TruthRow {
                gate: if key.must_be_safe() {
                    GateState::Safe
                } else {
                    GateState::Enabled
                },
                health: if key.health_must_be_fault() {
                    HealthState::Fault
                } else {
                    HealthState::Healthy
                },
                key,
                detection_path: "local-permit-and-rail-good".to_owned(),
                max_response_ns: 100,
                reset_authority: ResetAuthority::ExplicitSystemReset,
                status: EvidenceStatus::Pass,
                evidence_digest: evidence_digest.clone(),
            })
            .collect();
        let transition_rows = TransitionScenario::ALL
            .into_iter()
            .map(|scenario| TransitionRow {
                scenario,
                gate: GateState::Safe,
                health: HealthState::Fault,
                detection_path: "system-latch".to_owned(),
                max_response_ns: 100,
                reset_authority: ResetAuthority::ExplicitSystemReset,
                status: EvidenceStatus::Pass,
                evidence_digest: evidence_digest.clone(),
            })
            .collect();
        let fault_rows = FaultKind::ALL
            .into_iter()
            .map(|fault| FaultRow {
                fault,
                safe_state: GateState::Safe,
                detection_path: "independent-safe-demand".to_owned(),
                max_response_ns: 100,
                latent_risk: "diagnostic-only".to_owned(),
                reset_authority: ResetAuthority::ExplicitSystemReset,
                status: EvidenceStatus::Pass,
                evidence_digest: evidence_digest.clone(),
            })
            .collect();
        let requirement_ids: Vec<String> = (1..=23).map(|id| format!("R{id}")).collect();
        let owner_signoffs = SemanticRole::ALL
            .into_iter()
            .map(|role| OwnerSignoff {
                role,
                requirement_ids: requirement_ids.clone(),
                envelope_digest: envelope_digest.clone(),
                scope_digest: "e".repeat(64),
                signature_digest: "f".repeat(64),
                validity: SignoffValidity::Valid,
            })
            .collect();
        GateDriveQualificationPackage {
            schema_version: SCHEMA_VERSION,
            candidate,
            provenance: Provenance {
                source_revision: "rev-1".to_owned(),
                source_sha256: "1".repeat(64),
                test_conditions: "qualified-corners".to_owned(),
            },
            evidence_axes,
            truth_rows,
            transition_rows,
            fault_rows,
            owner_signoffs,
            preliminary_ruling: None,
        }
    }
    #[cfg_attr(test, test)]
    fn malformed_minimal_package_is_rejected_before_policy() {
        let package = GateDriveQualificationPackage {
            schema_version: SCHEMA_VERSION,
            candidate: CandidateEnvelope {
                candidate_id: "minimal".to_owned(),
                envelope_digest: "a".repeat(64),
                isolator_mpn: "wrong".to_owned(),
                local_driver_mpn: "driver".to_owned(),
                domains: vec![],
                construction_projection_digest: "b".repeat(64),
                allowed_transform_policy_digest: "c".repeat(64),
            },
            provenance: Provenance {
                source_revision: "rev".to_owned(),
                source_sha256: "d".repeat(64),
                test_conditions: "conditions".to_owned(),
            },
            evidence_axes: vec![],
            truth_rows: vec![],
            transition_rows: vec![],
            fault_rows: vec![],
            owner_signoffs: vec![],
            preliminary_ruling: None,
        };
        assert!(matches!(
            evaluate_gate_drive(&package),
            Err(QualificationError::InvalidCandidateIdentity)
        ));
    }
    #[cfg_attr(test, test)]
    fn generated_truth_space_is_finite_and_canonical() {
        let rows = TruthRowKey::all();
        assert_eq!(rows.len(), 2 * 2 * 3 * 2 * 2 * 3 * 2 * 3 * 3);
        assert!(rows.windows(2).all(|pair| pair[0].id() != pair[1].id()));
    }

    #[cfg_attr(test, test)]
    fn all_pass_stops_at_preliminary_review_without_a8() {
        let mut package = valid_package();
        package.evidence_axes[19].status = EvidenceStatus::Pending;
        package.evidence_axes[20].status = EvidenceStatus::Pending;
        let decision = evaluate_gate_drive(&package).unwrap();
        assert_eq!(decision.internal_stage, LifecycleStage::InternallyQualified);
        assert_eq!(
            decision.stage,
            LifecycleStage::EligibleForPreliminaryExternalReview
        );
    }

    #[cfg_attr(test, test)]
    fn failure_precedes_pending_and_reason_order_is_stable() {
        let mut package = valid_package();
        package.evidence_axes[0].status = EvidenceStatus::Pending;
        package.evidence_axes[1].status = EvidenceStatus::Fail;
        let decision = evaluate_gate_drive(&package).unwrap();
        assert_eq!(decision.stage, LifecycleStage::Rejected);
        assert_eq!(decision.reasons, vec!["identity.manufacturer_sources"]);
    }

    #[cfg_attr(test, test)]
    fn missing_truth_row_is_an_input_error_not_an_implicit_pass() {
        let mut package = valid_package();
        package.truth_rows.pop();
        assert!(matches!(
            evaluate_gate_drive(&package),
            Err(QualificationError::IncompleteTruthTable(_))
        ));
    }

    #[cfg_attr(test, test)]
    fn digest_mismatched_preliminary_receipt_cannot_approve() {
        let mut package = valid_package();
        package.preliminary_ruling = Some(PreliminaryRuling {
            envelope_digest: "9".repeat(64),
            disposition: AuthorityDisposition::Favorable,
            limitations: vec![],
        });
        assert!(matches!(
            evaluate_gate_drive(&package),
            Err(QualificationError::InvalidPreliminaryRuling(_))
        ));
    }

    #[cfg_attr(test, test)]
    fn matching_favorable_receipt_approves_only_compatible_limitations() {
        let mut package = valid_package();
        package.preliminary_ruling = Some(PreliminaryRuling {
            envelope_digest: package.candidate.envelope_digest.clone(),
            disposition: AuthorityDisposition::Favorable,
            limitations: vec![PreliminaryLimitation {
                id: "a8-1".to_owned(),
                scope: LimitationScope::Compatible,
                description: "candidate-only fixture use".to_owned(),
            }],
        });
        let decision = evaluate_gate_drive(&package).unwrap();
        assert_eq!(decision.stage, LifecycleStage::ConstructionEnvelopeApproved);
        assert_eq!(decision.limitations.len(), 1);
    }

    #[cfg_attr(test, test)]
    fn lifecycle_allows_only_internal_then_preliminary_authority() {
        assert_eq!(
            transition_stage(LifecycleStage::Draft, LifecycleEvent::InternalPass).unwrap(),
            LifecycleStage::InternallyQualified
        );
        assert_eq!(
            transition_stage(
                LifecycleStage::InternallyQualified,
                LifecycleEvent::SubmitForPreliminaryReview
            )
            .unwrap(),
            LifecycleStage::EligibleForPreliminaryExternalReview
        );
        assert_eq!(
            transition_stage(
                LifecycleStage::EligibleForPreliminaryExternalReview,
                LifecycleEvent::PreliminaryPass
            )
            .unwrap(),
            LifecycleStage::ConstructionEnvelopeApproved
        );
        assert!(
            transition_stage(
                LifecycleStage::ConstructionEnvelopeApproved,
                LifecycleEvent::PreliminaryPass
            )
            .is_err()
        );
    }

    fn valid_u7_package() -> PreliminaryAuthorityPackage {
        let envelope = "a".repeat(64);
        let projection = "b".repeat(64);
        let policy = "c".repeat(64);
        let evidence_bytes = b"u7-evidence".to_vec();
        let evidence_sha = sha256_hex(&evidence_bytes);
        let candidate = CandidateEnvelope {
            candidate_id: "iso7741-u7".to_owned(),
            envelope_digest: envelope.clone(),
            isolator_mpn: "ISO7741FQDWWRQ1".to_owned(),
            local_driver_mpn: "UCC27517AQDBVRQ1".to_owned(),
            domains: vec![GateDomain::HighSide, GateDomain::LowSide],
            construction_projection_digest: projection.clone(),
            allowed_transform_policy_digest: policy.clone(),
        };
        let object = EvidenceObject {
            id: "evidence".to_owned(),
            path: "power_pcb_dataset/qualification/iso7741_gate_drive/evidence.json".to_owned(),
            axis: "identity.exact_parts".to_owned(),
            status: EvidenceStatus::Pass,
            source_revision: "u7-test".to_owned(),
            source_sha256: evidence_sha.clone(),
            test_conditions: "synthetic".to_owned(),
            tool_identity: "u7-test".to_owned(),
            owner: "iso.verification".to_owned(),
            sha256: evidence_sha.clone(),
            bytes: evidence_bytes,
        };
        let evidence_axes = INTERNAL_AXES
            .iter()
            .map(|code| InternalEvidenceAxis {
                code: (*code).to_owned(),
                status: EvidenceStatus::Pass,
                evidence_digest: evidence_sha.clone(),
                owner: "iso.verification".to_owned(),
            })
            .collect();
        let role_requirements: [(&str, &[&str]); 7] = [
            (
                "iso.board_architecture",
                &["R1", "R2", "R3", "R4", "R19", "R21"],
            ),
            (
                "iso.electrical_power",
                &[
                    "R1", "R2", "R3", "R4", "R6", "R7", "R8", "R9", "R10", "R11", "R12", "R14",
                    "R15", "R16", "R17", "R22", "R23",
                ],
            ),
            ("iso.safety", &["R3", "R10", "R11", "R12", "R22", "R23"]),
            ("iso.pcb_layout", &["R5", "R13", "R14", "R15", "R16"]),
            ("iso.mechanical_thermal", &["R5", "R13", "R17"]),
            ("iso.sourcing", &["R5"]),
            ("iso.verification", &["R18", "R20", "R21", "R22", "R23"]),
        ];
        let scope_nodes = role_requirements
            .iter()
            .map(|(role, requirements)| {
                let node = ScopeNode {
                    id: format!("scope-{}", role.rsplit('.').next().unwrap_or("role")),
                    owner_role: (*role).to_owned(),
                    requirement_ids: requirements.iter().map(|id| (*id).to_owned()).collect(),
                    evidence_ids: vec!["evidence".to_owned()],
                    scope_digest: String::new(),
                };
                let digest = internal_scope_digest(&node, &BTreeMap::from([("evidence", &object)]));
                ScopeNode {
                    scope_digest: digest,
                    ..node
                }
            })
            .collect::<Vec<_>>();
        let signature_bytes = b"u7-signature".to_vec();
        let signature_sha = sha256_hex(&signature_bytes);
        let signature_artifacts = role_requirements
            .iter()
            .map(|(role, _)| SignatureArtifact {
                artifact_id: format!("sig-{}", role.rsplit('.').next().unwrap_or("role")),
                path: format!(
                    "power_pcb_dataset/qualification/iso7741_gate_drive/authority/signed/{}.sig",
                    role.rsplit('.').next().unwrap_or("role")
                ),
                sha256: signature_sha.clone(),
                signer_id: format!("signer-{}", role),
                signer_role: (*role).to_owned(),
                signed_scope: scope_nodes
                    .iter()
                    .find(|node| node.owner_role == *role)
                    .map(|node| node.scope_digest.clone())
                    .unwrap_or_default(),
                envelope_digest: envelope.clone(),
                verification_method: "synthetic".to_owned(),
                ingestion_record: "u7-test".to_owned(),
                bytes: signature_bytes.clone(),
            })
            .collect::<Vec<_>>();
        let owner_signoffs = role_requirements
            .iter()
            .map(|(role, requirements)| {
                let artifact = signature_artifacts
                    .iter()
                    .find(|item| item.signer_role == *role)
                    .unwrap();
                let scope = scope_nodes
                    .iter()
                    .find(|node| node.owner_role == *role)
                    .unwrap();
                InternalOwnerSignoff {
                    role: (*role).to_owned(),
                    signer_id: artifact.signer_id.clone(),
                    requirement_ids: requirements.iter().map(|id| (*id).to_owned()).collect(),
                    envelope_digest: envelope.clone(),
                    scope_node_id: scope.id.clone(),
                    scope_digest: scope.scope_digest.clone(),
                    status: EvidenceStatus::Pass,
                    signature_artifact: Some(SignatureArtifactRef {
                        artifact_id: artifact.artifact_id.clone(),
                        path: artifact.path.clone(),
                        sha256: artifact.sha256.clone(),
                        signer_id: artifact.signer_id.clone(),
                        signer_role: artifact.signer_role.clone(),
                        signed_scope: artifact.signed_scope.clone(),
                        envelope_digest: artifact.envelope_digest.clone(),
                        verification_method: artifact.verification_method.clone(),
                        ingestion_record: artifact.ingestion_record.clone(),
                    }),
                }
            })
            .collect();
        let internal = InternalEvidenceIndex {
            schema_version: SCHEMA_VERSION,
            candidate,
            provenance: Provenance {
                source_revision: "u7-test".to_owned(),
                source_sha256: "d".repeat(64),
                test_conditions: "synthetic".to_owned(),
            },
            evidence_axes,
            evidence_objects: vec![object],
            evidence_root_digest: digest_lines(["evidence".to_owned(), evidence_sha]),
            scope_nodes,
            owner_signoffs,
            signature_artifacts,
        };
        let mut submission = SubmissionIndex {
            schema_version: SCHEMA_VERSION,
            submission_id: "submission-u7".to_owned(),
            candidate_id: "iso7741-u7".to_owned(),
            envelope_digest: envelope.clone(),
            construction_projection_digest: projection.clone(),
            allowed_transform_policy_digest: policy.clone(),
            fixture_digest: "e".repeat(64),
            evidence_root_digest: internal.evidence_root_digest.clone(),
            internal_decision_digest: "f".repeat(64),
            evidence_revision: "u6".to_owned(),
            standard_question: "standard?".to_owned(),
            construction_question: "construction?".to_owned(),
            reproduction_instructions: "replay".to_owned(),
            owner_receipts: Vec::new(),
            submission_digest: "1".repeat(64),
        };
        submission.submission_digest = submission_content_digest(&submission);
        let receipt_bytes = b"a8-receipt".to_vec();
        let ruling = AuthorityRulingInput {
            schema_version: SCHEMA_VERSION,
            submission_digest: submission.submission_digest.clone(),
            candidate_id: submission.candidate_id.clone(),
            envelope_digest: envelope,
            construction_projection_digest: projection,
            allowed_transform_policy_digest: policy,
            disposition: AuthorityDisposition::Favorable,
            response_kind: AuthorityResponseKind::Construction,
            provider_id: "provider.example".to_owned(),
            signer_role: "iso.external_compliance".to_owned(),
            signed_scope_digest: submission.submission_digest.clone(),
            verification_method: "detached-signature".to_owned(),
            ingestion_record: "u7-test".to_owned(),
            receipt_artifact: Some(AuthorityReceiptArtifact {
                artifact_id: "a8".to_owned(),
                path:
                    "power_pcb_dataset/qualification/iso7741_gate_drive/authority/signed/a8.receipt"
                        .to_owned(),
                sha256: sha256_hex(&receipt_bytes),
                bytes: receipt_bytes,
            }),
            limitations: Vec::new(),
            invalidated_owner_scopes: Vec::new(),
            requested_identity_changes: Vec::new(),
            requested_construction_projection_digest: None,
            requested_allowed_transform_policy_digest: None,
        };
        PreliminaryAuthorityPackage {
            internal,
            submission_index: submission,
            preliminary_ruling: ruling,
        }
    }

    #[cfg_attr(test, test)]
    fn u7_rejected_internal_result_cannot_be_laundered_by_favorable_receipt() {
        let mut package = valid_u7_package();
        package.internal.evidence_axes[8].status = EvidenceStatus::Fail;
        let result = evaluate_preliminary_authority(&package).unwrap();
        assert_eq!(result.internal_stage, LifecycleStage::Rejected);
        assert_eq!(result.stage, LifecycleStage::Rejected);
    }

    #[cfg_attr(test, test)]
    fn u7_classifies_ambiguous_identity_and_evidence_only_requests() {
        let mut package = valid_u7_package();
        package
            .preliminary_ruling
            .limitations
            .push(PreliminaryLimitation {
                id: "scope".to_owned(),
                scope: LimitationScope::Ambiguous,
                description: "unclear".to_owned(),
            });
        assert_eq!(
            evaluate_preliminary_authority(&package).unwrap().stage,
            LifecycleStage::StoppedIndeterminate
        );
        let mut evidence_only = valid_u7_package();
        evidence_only.preliminary_ruling.response_kind = AuthorityResponseKind::EvidenceOnly;
        evidence_only.preliminary_ruling.invalidated_owner_scopes =
            vec!["iso.electrical_power".to_owned()];
        let result = evaluate_preliminary_authority(&evidence_only).unwrap();
        assert_eq!(result.stage, LifecycleStage::StoppedIndeterminate);
        assert_eq!(
            result.invalidated_owner_scopes,
            vec!["iso.electrical_power", "iso.verification"]
        );
        let mut identity = valid_u7_package();
        identity.preliminary_ruling.requested_identity_changes = vec!["footprint".to_owned()];
        assert_eq!(
            evaluate_preliminary_authority(&identity).unwrap().stage,
            LifecycleStage::Rejected
        );
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        (
            "owner_iso7741::tests::malformed_minimal_package_is_rejected_before_policy",
            malformed_minimal_package_is_rejected_before_policy,
        ),
        (
            "owner_iso7741::tests::generated_truth_space_is_finite_and_canonical",
            generated_truth_space_is_finite_and_canonical,
        ),
        (
            "owner_iso7741::tests::all_pass_stops_at_preliminary_review_without_a8",
            all_pass_stops_at_preliminary_review_without_a8,
        ),
        (
            "owner_iso7741::tests::failure_precedes_pending_and_reason_order_is_stable",
            failure_precedes_pending_and_reason_order_is_stable,
        ),
        (
            "owner_iso7741::tests::missing_truth_row_is_an_input_error_not_an_implicit_pass",
            missing_truth_row_is_an_input_error_not_an_implicit_pass,
        ),
        (
            "owner_iso7741::tests::digest_mismatched_preliminary_receipt_cannot_approve",
            digest_mismatched_preliminary_receipt_cannot_approve,
        ),
        (
            "owner_iso7741::tests::matching_favorable_receipt_approves_only_compatible_limitations",
            matching_favorable_receipt_approves_only_compatible_limitations,
        ),
        (
            "owner_iso7741::tests::lifecycle_allows_only_internal_then_preliminary_authority",
            lifecycle_allows_only_internal_then_preliminary_authority,
        ),
        (
            "owner_iso7741::tests::u7_rejected_internal_result_cannot_be_laundered_by_favorable_receipt",
            u7_rejected_internal_result_cannot_be_laundered_by_favorable_receipt,
        ),
        (
            "owner_iso7741::tests::u7_classifies_ambiguous_identity_and_evidence_only_requests",
            u7_classifies_ambiguous_identity_and_evidence_only_requests,
        ),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}
