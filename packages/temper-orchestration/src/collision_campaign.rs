//! Valid-state core for bounded collision-aware placement campaigns.
//!
//! Each public transition consumes its phase.  Consequently a terminal
//! verdict cannot be resumed and a candidate cannot be audited twice in
//! safe Rust.  Primitive parsing is confined to validated constructors.

use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet};
use std::fmt;
use temper_geometry::body_collision::AREA_TOLERANCE_MM2;
use temper_geometry::rotation_quadrant::RotationQuadrant;

#[cfg(feature = "python")]
use pyo3::exceptions::{PyRuntimeError, PyTypeError, PyValueError};
#[cfg(feature = "python")]
use pyo3::prelude::*;
#[cfg(feature = "python")]
use pyo3::types::{PyAny, PyDict};

const CHECKPOINT_MAGIC: &[u8; 8] = b"TCAMP001";
pub const MODEL_UNITS_PER_MM: i64 = 1_000;

#[cfg(feature = "python")]
#[pyfunction]
pub fn collision_campaign_model_units_per_mm() -> i64 {
    MODEL_UNITS_PER_MM
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum CampaignError {
    InvalidValue(&'static str),
    MissingPose(String),
    DuplicateComponent(String),
    DuplicateCut,
    ConflictingCut,
    ForeignIdentity { expected: String, actual: String },
    TerminalState,
    Checkpoint(String),
}

impl fmt::Display for CampaignError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{self:?}")
    }
}
impl std::error::Error for CampaignError {}

fn nonempty(value: &str, name: &'static str) -> Result<String, CampaignError> {
    if value.trim().is_empty() {
        Err(CampaignError::InvalidValue(name))
    } else {
        Ok(value.to_owned())
    }
}

#[derive(Debug, Clone, PartialEq, Eq, PartialOrd, Ord, Hash, Serialize, Deserialize)]
pub struct ComponentRef(String);
impl ComponentRef {
    pub fn new(raw: &str) -> Result<Self, CampaignError> {
        Ok(Self(nonempty(raw, "component reference")?))
    }
    pub fn as_str(&self) -> &str {
        &self.0
    }
}

#[derive(Debug, Clone, PartialEq, Eq, PartialOrd, Ord, Hash, Serialize, Deserialize)]
pub struct InputIdentity {
    board: String,
    rules: String,
    solver: String,
    axis: String,
}
impl InputIdentity {
    pub fn new(board: &str, rules: &str, solver: &str, axis: &str) -> Result<Self, CampaignError> {
        Ok(Self {
            board: nonempty(board, "board identity")?,
            rules: nonempty(rules, "rules identity")?,
            solver: nonempty(solver, "solver identity")?,
            axis: nonempty(axis, "axis identity")?,
        })
    }
    fn label(&self) -> String {
        format!(
            "{}:{}:{}:{}",
            self.board, self.rules, self.solver, self.axis
        )
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash, Serialize, Deserialize)]
pub struct ModelCoordinate(i64);
impl ModelCoordinate {
    pub fn new(raw: i64) -> Result<Self, CampaignError> {
        Ok(Self(raw))
    }
    pub fn from_mm(mm: f64) -> Result<Self, CampaignError> {
        if !mm.is_finite() {
            return Err(CampaignError::InvalidValue("model coordinate"));
        }
        let scaled = mm * MODEL_UNITS_PER_MM as f64;
        if scaled < i64::MIN as f64 || scaled > i64::MAX as f64 {
            return Err(CampaignError::InvalidValue("model coordinate"));
        }
        Ok(Self(scaled.round() as i64))
    }
    pub fn raw(self) -> i64 {
        self.0
    }
    pub fn to_mm(self) -> f64 {
        self.0 as f64 / MODEL_UNITS_PER_MM as f64
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash, Serialize, Deserialize)]
pub struct ExactPose {
    x: ModelCoordinate,
    y: ModelCoordinate,
    rotation_index: u8,
}
impl ExactPose {
    pub fn new(
        x: ModelCoordinate,
        y: ModelCoordinate,
        rotation: RotationQuadrant,
    ) -> Result<Self, CampaignError> {
        Ok(Self {
            x,
            y,
            rotation_index: rotation.index(),
        })
    }
    pub fn from_raw(x: i64, y: i64, rotation: i64) -> Result<Self, CampaignError> {
        if !(0..=3).contains(&rotation) {
            return Err(CampaignError::InvalidValue("rotation quadrant"));
        }
        Self::new(
            ModelCoordinate::new(x)?,
            ModelCoordinate::new(y)?,
            RotationQuadrant::from_raw(rotation),
        )
    }
    pub fn x(self) -> ModelCoordinate {
        self.x
    }
    pub fn y(self) -> ModelCoordinate {
        self.y
    }
    pub fn rotation(self) -> RotationQuadrant {
        RotationQuadrant::from_raw(self.rotation_index as i64)
    }
}

#[derive(Debug, Clone, PartialEq, Eq, PartialOrd, Ord, Hash, Serialize, Deserialize)]
pub struct ComponentPair {
    first: ComponentRef,
    second: ComponentRef,
}
impl ComponentPair {
    fn new(a: ComponentRef, b: ComponentRef) -> Result<Self, CampaignError> {
        if a == b {
            return Err(CampaignError::InvalidValue("collision pair"));
        }
        Ok(if a < b {
            Self {
                first: a,
                second: b,
            }
        } else {
            Self {
                first: b,
                second: a,
            }
        })
    }
    pub fn first(&self) -> &ComponentRef {
        &self.first
    }
    pub fn second(&self) -> &ComponentRef {
        &self.second
    }
}

#[derive(Debug, Clone, PartialEq)]
pub struct CollisionWitness {
    pair: ComponentPair,
    area_mm2: f64,
    candidate_digest: String,
}
impl CollisionWitness {
    pub fn new(a: &str, b: &str, area_mm2: f64, digest: &str) -> Result<Self, CampaignError> {
        // Keep the campaign witness domain aligned with the geometry
        // authority: boundary contact and sub-tolerance Boolean noise are
        // not collisions and must never become exact-assignment cuts.
        if !area_mm2.is_finite() || area_mm2 <= AREA_TOLERANCE_MM2 {
            return Err(CampaignError::InvalidValue("overlap area"));
        }
        Ok(Self {
            pair: ComponentPair::new(ComponentRef::new(a)?, ComponentRef::new(b)?)?,
            area_mm2,
            candidate_digest: nonempty(digest, "candidate digest")?,
        })
    }
}

#[derive(Debug, Clone, PartialEq, Eq, PartialOrd, Ord, Hash, Serialize, Deserialize)]
pub struct CutKey {
    identity: InputIdentity,
    pair: ComponentPair,
    first_pose: ExactPose,
    second_pose: ExactPose,
}

#[derive(Debug, Clone, PartialEq)]
pub struct CollisionCut {
    key: CutKey,
    area_mm2: f64,
    candidate_digest: String,
}
impl CollisionCut {
    pub fn key(&self) -> &CutKey {
        &self.key
    }
    pub fn pair(&self) -> &ComponentPair {
        &self.key.pair
    }
    pub fn is_from(&self, identity: &InputIdentity) -> bool {
        &self.key.identity == identity
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub struct CampaignLimits {
    max_rounds: u32,
    round_budget_ms: u64,
}
impl CampaignLimits {
    pub fn new(max_rounds: u32, round_budget_ms: u64) -> Result<Self, CampaignError> {
        if max_rounds == 0 || round_budget_ms == 0 {
            return Err(CampaignError::InvalidValue("campaign limits"));
        }
        Ok(Self {
            max_rounds,
            round_budget_ms,
        })
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum GateOutcome {
    Passed,
    Trusted,
    Rejected(String),
}
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct AuditGates {
    creepage: GateOutcome,
    body: GateOutcome,
    provenance: GateOutcome,
}
impl AuditGates {
    pub fn new(creepage: GateOutcome, body: GateOutcome, provenance: GateOutcome) -> Self {
        Self {
            creepage,
            body,
            provenance,
        }
    }
    pub fn all_passed() -> Self {
        Self::new(
            GateOutcome::Passed,
            GateOutcome::Passed,
            GateOutcome::Trusted,
        )
    }
    fn rejection(&self) -> Option<String> {
        let gate_rejection = [&self.creepage, &self.body]
            .into_iter()
            .find_map(|g| match g {
                GateOutcome::Rejected(reason) => Some(reason.clone()),
                _ => None,
            });
        gate_rejection.or_else(|| match &self.provenance {
            GateOutcome::Trusted => None,
            GateOutcome::Rejected(reason) => Some(reason.clone()),
            GateOutcome::Passed => Some("provenance gate is not trusted".to_owned()),
        })
    }

    /// A body collision may legitimately drive another refinement round;
    /// failed creepage or untrusted provenance may not.
    fn refinement_blocker(&self) -> Option<String> {
        match &self.creepage {
            GateOutcome::Rejected(reason) => return Some(reason.clone()),
            GateOutcome::Passed | GateOutcome::Trusted => {}
        }
        match &self.provenance {
            GateOutcome::Trusted => None,
            GateOutcome::Rejected(reason) => Some(reason.clone()),
            GateOutcome::Passed => Some("provenance gate is not trusted".to_owned()),
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct CampaignState {
    identity: InputIdentity,
    components: BTreeSet<ComponentRef>,
    limits: CampaignLimits,
    round: u32,
    cuts: Vec<StoredCut>,
}
impl CampaignState {
    fn collision_cuts(&self) -> Vec<CollisionCut> {
        self.cuts
            .iter()
            .map(|cut| CollisionCut {
                key: cut.key.clone(),
                area_mm2: cut.area_mm2,
                candidate_digest: cut.candidate_digest.clone(),
            })
            .collect()
    }
}
#[derive(Debug, Clone, Serialize, Deserialize)]
struct StoredCut {
    key: CutKey,
    area_mm2: f64,
    candidate_digest: String,
}

#[derive(Debug, Clone)]
pub struct Prepared {
    state: CampaignState,
}
impl Prepared {
    pub fn new(
        identity: InputIdentity,
        refs: Vec<&str>,
        limits: CampaignLimits,
    ) -> Result<Self, CampaignError> {
        let mut components = BTreeSet::new();
        for raw in refs {
            let reference = ComponentRef::new(raw)?;
            if !components.insert(reference.clone()) {
                return Err(CampaignError::DuplicateComponent(reference.0));
            }
        }
        if components.is_empty() {
            return Err(CampaignError::InvalidValue("component coverage"));
        }
        Ok(Self {
            state: CampaignState {
                identity,
                components,
                limits,
                round: 0,
                cuts: vec![],
            },
        })
    }
    pub fn start_solving(self) -> Result<Solving, CampaignError> {
        Ok(Solving { state: self.state })
    }
    pub fn checkpoint(&self) -> CampaignCheckpoint {
        CampaignCheckpoint {
            state: self.state.clone(),
            terminal: None,
        }
    }

    /// Return the validated frontier restored from a checkpoint.  The
    /// campaign adapter uses this to replay every cut into the next fresh
    /// CP-SAT model; callers cannot mutate the underlying state.
    pub fn cuts(&self) -> Vec<CollisionCut> {
        self.state.collision_cuts()
    }

    pub fn round(&self) -> u32 {
        self.state.round
    }
}

#[derive(Debug)]
pub struct Solving {
    state: CampaignState,
}
impl Solving {
    pub fn complete_candidate(
        self,
        poses: Vec<(&str, ExactPose)>,
    ) -> Result<Candidate, CampaignError> {
        let mut map = BTreeMap::new();
        for (raw, pose) in poses {
            let r = ComponentRef::new(raw)?;
            if map.insert(r.clone(), pose).is_some() {
                return Err(CampaignError::DuplicateComponent(r.0));
            }
        }
        for r in &self.state.components {
            if !map.contains_key(r) {
                return Err(CampaignError::MissingPose(r.0.clone()));
            }
        }
        if map.len() != self.state.components.len() {
            return Err(CampaignError::InvalidValue("foreign candidate component"));
        }
        Ok(Candidate {
            state: self.state,
            poses: map,
        })
    }
}

#[derive(Debug)]
pub struct Candidate {
    state: CampaignState,
    poses: BTreeMap<ComponentRef, ExactPose>,
}
impl Candidate {
    fn checkpoint(&self) -> CampaignCheckpoint {
        CampaignCheckpoint {
            state: self.state.clone(),
            terminal: None,
        }
    }

    pub fn audit(
        self,
        gates: AuditGates,
        witnesses: Vec<CollisionWitness>,
    ) -> Result<AuditDecision, CampaignError> {
        if witnesses.is_empty() {
            return Ok(match gates.rejection() {
                Some(reason) => {
                    AuditDecision::Terminal(TerminalVerdict::VerifierRejected { reason })
                }
                None => AuditDecision::Terminal(TerminalVerdict::Accepted {
                    rounds: self.state.round + 1,
                }),
            });
        }
        if let Some(reason) = gates.refinement_blocker() {
            return Ok(AuditDecision::Terminal(TerminalVerdict::VerifierRejected {
                reason,
            }));
        }
        let mut state = self.state;
        let mut added = 0;
        let mut cut_indexes: BTreeMap<CutKey, usize> = state
            .cuts
            .iter()
            .enumerate()
            .map(|(index, cut)| (cut.key.clone(), index))
            .collect();
        for witness in witnesses {
            let first_pose = *self
                .poses
                .get(witness.pair.first())
                .ok_or_else(|| CampaignError::MissingPose(witness.pair.first().0.clone()))?;
            let second_pose = *self
                .poses
                .get(witness.pair.second())
                .ok_or_else(|| CampaignError::MissingPose(witness.pair.second().0.clone()))?;
            let key = CutKey {
                identity: state.identity.clone(),
                pair: witness.pair,
                first_pose,
                second_pose,
            };
            if let Some(existing_index) = cut_indexes.get(&key) {
                let existing = &state.cuts[*existing_index];
                if existing.area_mm2.to_bits() == witness.area_mm2.to_bits()
                    && existing.candidate_digest == witness.candidate_digest
                {
                    continue;
                }
                return Err(CampaignError::ConflictingCut);
            }
            state.cuts.push(StoredCut {
                key: key.clone(),
                area_mm2: witness.area_mm2,
                candidate_digest: witness.candidate_digest,
            });
            cut_indexes.insert(key, state.cuts.len() - 1);
            added += 1;
        }
        if added == 0 {
            return Ok(AuditDecision::Terminal(TerminalVerdict::NoProgress {
                rounds: state.round + 1,
            }));
        }
        if state.round + 1 >= state.limits.max_rounds {
            return Ok(AuditDecision::Terminal(TerminalVerdict::RoundLimit {
                rounds: state.round + 1,
            }));
        }
        state.round += 1;
        Ok(AuditDecision::Refining(Refining { state }))
    }
}

#[derive(Debug)]
pub struct Refining {
    state: CampaignState,
}
impl Refining {
    pub fn cuts(&self) -> Vec<CollisionCut> {
        self.state.collision_cuts()
    }
    pub fn next_round(self) -> Result<Solving, CampaignError> {
        Ok(Solving { state: self.state })
    }
    pub fn checkpoint(&self) -> CampaignCheckpoint {
        CampaignCheckpoint {
            state: self.state.clone(),
            terminal: None,
        }
    }
}

#[derive(Debug)]
pub enum AuditDecision {
    Refining(Refining),
    Terminal(TerminalVerdict),
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub enum TerminalVerdict {
    Accepted { rounds: u32 },
    VerifierRejected { reason: String },
    NoProgress { rounds: u32 },
    RoundLimit { rounds: u32 },
    InvalidExperiment { reason: String },
}
impl TerminalVerdict {
    pub fn resume(&self) -> Result<Prepared, CampaignError> {
        Err(CampaignError::TerminalState)
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CampaignCheckpoint {
    state: CampaignState,
    #[serde(default)]
    terminal: Option<TerminalVerdict>,
}
impl CampaignCheckpoint {
    pub fn to_bytes(&self) -> Result<Vec<u8>, CampaignError> {
        let payload =
            serde_json::to_vec(self).map_err(|e| CampaignError::Checkpoint(e.to_string()))?;
        let mut bytes = CHECKPOINT_MAGIC.to_vec();
        bytes.extend(payload);
        Ok(bytes)
    }
    pub fn from_bytes(bytes: &[u8]) -> Result<Self, CampaignError> {
        if !bytes.starts_with(CHECKPOINT_MAGIC) {
            return Err(CampaignError::Checkpoint(
                "unknown checkpoint version".into(),
            ));
        }
        let checkpoint = serde_json::from_slice::<Self>(&bytes[CHECKPOINT_MAGIC.len()..])
            .map_err(|e| CampaignError::Checkpoint(e.to_string()))?;
        validate_checkpoint_state(&checkpoint.state)?;
        Ok(checkpoint)
    }
    pub fn restore_for(&self, identity: &InputIdentity) -> Result<Prepared, CampaignError> {
        self.validate_identity(identity)?;
        if self.terminal.is_some() {
            return Err(CampaignError::TerminalState);
        }
        Ok(Prepared {
            state: self.state.clone(),
        })
    }

    /// Validate the input identity without attempting to resume the phase.
    /// Terminal checkpoints remain identity-bound even though they cannot be
    /// restored into a live campaign.
    pub fn validate_identity(&self, identity: &InputIdentity) -> Result<(), CampaignError> {
        if &self.state.identity != identity {
            return Err(CampaignError::ForeignIdentity {
                expected: identity.label(),
                actual: self.state.identity.label(),
            });
        }
        Ok(())
    }

    pub fn terminal(&self) -> Option<&TerminalVerdict> {
        self.terminal.as_ref()
    }
}

fn validate_checkpoint_state(state: &CampaignState) -> Result<(), CampaignError> {
    InputIdentity::new(
        &state.identity.board,
        &state.identity.rules,
        &state.identity.solver,
        &state.identity.axis,
    )?;
    CampaignLimits::new(state.limits.max_rounds, state.limits.round_budget_ms)?;
    if state.components.is_empty() || state.round >= state.limits.max_rounds {
        return Err(CampaignError::Checkpoint("invalid campaign phase".into()));
    }
    for component in &state.components {
        ComponentRef::new(component.as_str())?;
    }
    let mut keys = BTreeSet::new();
    for cut in &state.cuts {
        let canonical_pair =
            ComponentPair::new(cut.key.pair.first.clone(), cut.key.pair.second.clone())
                .map_err(|_| CampaignError::Checkpoint("invalid collision pair".into()))?;
        if canonical_pair != cut.key.pair {
            return Err(CampaignError::Checkpoint(
                "collision pair is not canonical".into(),
            ));
        }
        for pose in [&cut.key.first_pose, &cut.key.second_pose] {
            ExactPose::from_raw(pose.x.raw(), pose.y.raw(), pose.rotation_index as i64)
                .map_err(|_| CampaignError::Checkpoint("invalid collision pose".into()))?;
        }
        if cut.key.identity != state.identity
            || !state.components.contains(cut.key.pair.first())
            || !state.components.contains(cut.key.pair.second())
            || !cut.area_mm2.is_finite()
            || cut.area_mm2 <= AREA_TOLERANCE_MM2
            || cut.candidate_digest.trim().is_empty()
        {
            return Err(CampaignError::Checkpoint("invalid collision cut".into()));
        }
        if !keys.insert(cut.key.clone()) {
            return Err(CampaignError::Checkpoint("duplicate collision cut".into()));
        }
    }
    Ok(())
}

// ---------------------------------------------------------------------------
// PyO3 boundary
// ---------------------------------------------------------------------------

/// The Python surface deliberately has one wrapper per Rust phase.  The
/// `Option` is not a convenience cache: taking it is the generation token.
/// Every consuming method takes the token before entering the Rust
/// transition, so all Python aliases of the old object observe the same
/// consumed handle after the call returns (or fails).
#[cfg(feature = "python")]
#[pyclass(
    module = "temper_orchestration",
    name = "CollisionCampaignPrepared",
    skip_from_py_object
)]
pub struct PyPrepared {
    inner: Option<Prepared>,
}

#[cfg(feature = "python")]
#[pyclass(
    module = "temper_orchestration",
    name = "CollisionCampaignSolving",
    skip_from_py_object
)]
pub struct PySolving {
    inner: Option<Solving>,
}

#[cfg(feature = "python")]
#[pyclass(
    module = "temper_orchestration",
    name = "CollisionCampaignCandidate",
    skip_from_py_object
)]
pub struct PyCandidate {
    inner: Option<Candidate>,
}

#[cfg(feature = "python")]
#[pyclass(
    module = "temper_orchestration",
    name = "CollisionCampaignRefining",
    skip_from_py_object
)]
pub struct PyRefining {
    inner: Option<Refining>,
}

#[cfg(feature = "python")]
#[pyclass(
    module = "temper_orchestration",
    name = "CollisionCampaignDecision",
    skip_from_py_object
)]
pub struct PyAuditDecision {
    inner: Option<AuditDecision>,
    checkpoint: Option<CampaignCheckpoint>,
}

#[cfg(feature = "python")]
#[pyclass(
    frozen,
    module = "temper_orchestration",
    name = "CollisionCampaignTerminalVerdict",
    skip_from_py_object
)]
pub struct PyTerminalVerdict {
    inner: TerminalVerdict,
}

#[cfg(feature = "python")]
#[pyclass(
    frozen,
    module = "temper_orchestration",
    name = "CollisionCampaignCut",
    skip_from_py_object
)]
pub struct PyCollisionCut {
    inner: CollisionCut,
}

#[cfg(feature = "python")]
#[pyclass(
    frozen,
    module = "temper_orchestration",
    name = "CollisionCampaignCheckpoint",
    skip_from_py_object
)]
pub struct PyCheckpoint {
    inner: CampaignCheckpoint,
}

#[cfg(feature = "python")]
fn consumed_error() -> PyErr {
    PyRuntimeError::new_err(
        "collision campaign handle has been consumed; use the handle returned by the transition",
    )
}

#[cfg(feature = "python")]
fn take_handle<T>(slot: &mut Option<T>) -> PyResult<T> {
    slot.take().ok_or_else(consumed_error)
}

#[cfg(feature = "python")]
fn campaign_error(error: CampaignError) -> PyErr {
    PyValueError::new_err(error.to_string())
}

#[cfg(feature = "python")]
fn parse_gate(value: &Bound<'_, PyAny>, allow_trusted: bool) -> PyResult<GateOutcome> {
    if let Ok(value) = value.extract::<bool>() {
        return Ok(if value {
            GateOutcome::Passed
        } else {
            GateOutcome::Rejected("gate rejected".to_owned())
        });
    }
    let value = value
        .extract::<String>()
        .map_err(|_| PyTypeError::new_err("gate outcome must be a bool or a status string"))?;
    let status = value.trim();
    if status.eq_ignore_ascii_case("passed") || status.eq_ignore_ascii_case("accepted") {
        return Ok(GateOutcome::Passed);
    }
    if allow_trusted && status.eq_ignore_ascii_case("trusted") {
        return Ok(GateOutcome::Trusted);
    }
    if let Some(reason) = status.strip_prefix("rejected:") {
        let reason = reason.trim();
        if reason.is_empty() {
            return Err(PyValueError::new_err(
                "rejected gate outcome must include a reason",
            ));
        }
        return Ok(GateOutcome::Rejected(reason.to_owned()));
    }
    Err(PyValueError::new_err(
        "gate outcome must be 'passed', 'trusted', or 'rejected:<reason>'",
    ))
}

#[cfg(feature = "python")]
fn parse_poses(value: &Bound<'_, PyAny>) -> PyResult<Vec<(String, ExactPose)>> {
    // A mapping is the production shape.  Primitive values are copied into
    // owned Rust values; no Python object is retained by the campaign.
    let dict = value.cast::<PyDict>().map_err(|_| {
        PyTypeError::new_err("candidate poses must be a dict of ref -> (x, y, rotation)")
    })?;
    let mut parsed = Vec::with_capacity(dict.len());
    for (reference, pose) in dict.iter() {
        let reference = reference.extract::<String>()?;
        let (x, y, rotation) = pose.extract::<(i64, i64, i64)>().map_err(|_| {
            PyTypeError::new_err("each candidate pose must be an (x, y, rotation) integer tuple")
        })?;
        let exact = ExactPose::from_raw(x, y, rotation).map_err(campaign_error)?;
        parsed.push((reference, exact));
    }
    Ok(parsed)
}

#[cfg(feature = "python")]
fn parse_witnesses(
    witnesses: Vec<(String, String, f64, String)>,
) -> Result<Vec<CollisionWitness>, PyErr> {
    witnesses
        .into_iter()
        .map(|(a, b, area, digest)| {
            CollisionWitness::new(&a, &b, area, &digest).map_err(campaign_error)
        })
        .collect()
}

#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(signature = (board, rules, solver, axis, components, max_rounds, round_budget_ms))]
#[expect(
    clippy::too_many_arguments,
    reason = "the pyo3 constructor receives the four-part evidence identity and two explicit limits"
)]
pub fn prepare_collision_campaign(
    py: Python<'_>,
    board: String,
    rules: String,
    solver: String,
    axis: String,
    components: Vec<String>,
    max_rounds: u32,
    round_budget_ms: u64,
) -> PyResult<Py<PyPrepared>> {
    let identity = InputIdentity::new(&board, &rules, &solver, &axis).map_err(campaign_error)?;
    let refs = components.iter().map(String::as_str).collect();
    let limits = CampaignLimits::new(max_rounds, round_budget_ms).map_err(campaign_error)?;
    let prepared = Prepared::new(identity, refs, limits).map_err(campaign_error)?;
    Py::new(
        py,
        PyPrepared {
            inner: Some(prepared),
        },
    )
}

#[cfg(feature = "python")]
#[pymethods]
impl PyPrepared {
    #[getter]
    fn round(&self) -> PyResult<u32> {
        let prepared = self.inner.as_ref().ok_or_else(consumed_error)?;
        Ok(prepared.round())
    }

    #[getter]
    fn max_rounds(&self) -> PyResult<u32> {
        let prepared = self.inner.as_ref().ok_or_else(consumed_error)?;
        Ok(prepared.state.limits.max_rounds)
    }

    #[getter]
    fn round_budget_ms(&self) -> PyResult<u64> {
        let prepared = self.inner.as_ref().ok_or_else(consumed_error)?;
        Ok(prepared.state.limits.round_budget_ms)
    }

    fn start_solving(&mut self, py: Python<'_>) -> PyResult<Py<PySolving>> {
        let prepared = take_handle(&mut self.inner)?;
        let solving = prepared.start_solving().map_err(campaign_error)?;
        Py::new(
            py,
            PySolving {
                inner: Some(solving),
            },
        )
    }

    fn checkpoint(&self, py: Python<'_>) -> PyResult<Py<PyCheckpoint>> {
        let prepared = self.inner.as_ref().ok_or_else(consumed_error)?;
        Py::new(
            py,
            PyCheckpoint {
                inner: prepared.checkpoint(),
            },
        )
    }

    fn cuts(&self, py: Python<'_>) -> PyResult<Vec<Py<PyCollisionCut>>> {
        let prepared = self.inner.as_ref().ok_or_else(consumed_error)?;
        prepared
            .cuts()
            .into_iter()
            .map(|cut| Py::new(py, PyCollisionCut { inner: cut }))
            .collect()
    }
}

#[cfg(feature = "python")]
#[pymethods]
impl PySolving {
    fn complete_candidate(
        &mut self,
        py: Python<'_>,
        poses: &Bound<'_, PyAny>,
    ) -> PyResult<Py<PyCandidate>> {
        let poses = parse_poses(poses)?;
        let solving = take_handle(&mut self.inner)?;
        let candidate = solving
            .complete_candidate(
                poses
                    .iter()
                    .map(|(reference, pose)| (reference.as_str(), *pose))
                    .collect(),
            )
            .map_err(campaign_error)?;
        Py::new(
            py,
            PyCandidate {
                inner: Some(candidate),
            },
        )
    }
}

#[cfg(feature = "python")]
#[pymethods]
impl PyCandidate {
    fn audit(
        &mut self,
        py: Python<'_>,
        creepage: &Bound<'_, PyAny>,
        body: &Bound<'_, PyAny>,
        provenance: &Bound<'_, PyAny>,
        witnesses: Vec<(String, String, f64, String)>,
    ) -> PyResult<Py<PyAuditDecision>> {
        let gates = AuditGates::new(
            parse_gate(creepage, false)?,
            parse_gate(body, false)?,
            parse_gate(provenance, true)?,
        );
        let witnesses = parse_witnesses(witnesses)?;
        let checkpoint = {
            let candidate_ref = self.inner.as_ref().ok_or_else(consumed_error)?;
            Some(candidate_ref.checkpoint())
        };
        let candidate = take_handle(&mut self.inner)?;
        let decision = candidate.audit(gates, witnesses).map_err(campaign_error)?;
        Py::new(
            py,
            PyAuditDecision {
                inner: Some(decision),
                checkpoint,
            },
        )
    }
}

#[cfg(feature = "python")]
#[pymethods]
impl PyAuditDecision {
    #[getter]
    fn kind(&self) -> PyResult<&'static str> {
        match self.inner.as_ref().ok_or_else(consumed_error)? {
            AuditDecision::Refining(_) => Ok("refining"),
            AuditDecision::Terminal(_) => Ok("terminal"),
        }
    }

    fn take_refining(&mut self, py: Python<'_>) -> PyResult<Py<PyRefining>> {
        if matches!(self.inner.as_ref(), Some(AuditDecision::Terminal(_))) {
            return Err(PyValueError::new_err(
                "campaign decision is terminal, not refining",
            ));
        }
        match take_handle(&mut self.inner)? {
            AuditDecision::Refining(refining) => Py::new(
                py,
                PyRefining {
                    inner: Some(refining),
                },
            ),
            AuditDecision::Terminal(_) => Err(PyValueError::new_err(
                "campaign decision is terminal, not refining",
            )),
        }
    }

    fn take_terminal(&mut self, py: Python<'_>) -> PyResult<Py<PyTerminalVerdict>> {
        if matches!(self.inner.as_ref(), Some(AuditDecision::Refining(_))) {
            return Err(PyValueError::new_err(
                "campaign decision is refining, not terminal",
            ));
        }
        match take_handle(&mut self.inner)? {
            AuditDecision::Terminal(terminal) => Py::new(py, PyTerminalVerdict { inner: terminal }),
            AuditDecision::Refining(_) => Err(PyValueError::new_err(
                "campaign decision is refining, not terminal",
            )),
        }
    }

    /// Return an immutable terminal checkpoint before consuming this
    /// decision.  The state and terminal verdict are serialized by Rust;
    /// Python receives only the opaque checkpoint wrapper.
    fn terminal_checkpoint(&self, py: Python<'_>) -> PyResult<Py<PyCheckpoint>> {
        let decision = self.inner.as_ref().ok_or_else(consumed_error)?;
        let terminal = match decision {
            AuditDecision::Terminal(value) => value.clone(),
            AuditDecision::Refining(_) => {
                return Err(PyValueError::new_err(
                    "campaign decision is refining, not terminal",
                ));
            }
        };
        let checkpoint = self.checkpoint.as_ref().ok_or_else(consumed_error)?;
        Py::new(
            py,
            PyCheckpoint {
                inner: CampaignCheckpoint {
                    state: checkpoint.state.clone(),
                    terminal: Some(terminal),
                },
            },
        )
    }
}

#[cfg(feature = "python")]
#[pymethods]
impl PyRefining {
    fn next_round(&mut self, py: Python<'_>) -> PyResult<Py<PySolving>> {
        let refining = take_handle(&mut self.inner)?;
        let solving = refining.next_round().map_err(campaign_error)?;
        Py::new(
            py,
            PySolving {
                inner: Some(solving),
            },
        )
    }

    fn cuts(&self, py: Python<'_>) -> PyResult<Vec<Py<PyCollisionCut>>> {
        let refining = self.inner.as_ref().ok_or_else(consumed_error)?;
        refining
            .cuts()
            .into_iter()
            .map(|cut| Py::new(py, PyCollisionCut { inner: cut }))
            .collect()
    }

    fn checkpoint(&self, py: Python<'_>) -> PyResult<Py<PyCheckpoint>> {
        let refining = self.inner.as_ref().ok_or_else(consumed_error)?;
        Py::new(
            py,
            PyCheckpoint {
                inner: refining.checkpoint(),
            },
        )
    }
}

#[cfg(feature = "python")]
#[pymethods]
impl PyTerminalVerdict {
    #[getter]
    fn kind(&self) -> &'static str {
        match self.inner {
            TerminalVerdict::Accepted { .. } => "accepted",
            TerminalVerdict::VerifierRejected { .. } => "verifier_rejected",
            TerminalVerdict::NoProgress { .. } => "no_progress",
            TerminalVerdict::RoundLimit { .. } => "round_limit",
            TerminalVerdict::InvalidExperiment { .. } => "invalid_experiment",
        }
    }

    #[getter]
    fn rounds(&self) -> Option<u32> {
        match self.inner {
            TerminalVerdict::Accepted { rounds }
            | TerminalVerdict::NoProgress { rounds }
            | TerminalVerdict::RoundLimit { rounds } => Some(rounds),
            TerminalVerdict::VerifierRejected { .. }
            | TerminalVerdict::InvalidExperiment { .. } => None,
        }
    }

    #[getter]
    fn reason(&self) -> Option<&str> {
        match &self.inner {
            TerminalVerdict::VerifierRejected { reason }
            | TerminalVerdict::InvalidExperiment { reason } => Some(reason),
            _ => None,
        }
    }

    /// Terminal verdicts are closed.  This method exists to make attempted
    /// resume explicit at the Python boundary and always fails.
    fn resume(&self) -> PyResult<()> {
        self.inner.resume().map(|_| ()).map_err(campaign_error)
    }
}

#[cfg(feature = "python")]
#[pymethods]
impl PyCollisionCut {
    #[getter]
    fn first(&self) -> &str {
        self.inner.key.pair.first.as_str()
    }

    #[getter]
    fn second(&self) -> &str {
        self.inner.key.pair.second.as_str()
    }

    #[getter]
    fn x_first(&self) -> i64 {
        self.inner.key.first_pose.x.raw()
    }

    #[getter]
    fn y_first(&self) -> i64 {
        self.inner.key.first_pose.y.raw()
    }

    #[getter]
    fn rotation_first(&self) -> u8 {
        self.inner.key.first_pose.rotation_index
    }

    #[getter]
    fn x_second(&self) -> i64 {
        self.inner.key.second_pose.x.raw()
    }

    #[getter]
    fn y_second(&self) -> i64 {
        self.inner.key.second_pose.y.raw()
    }

    #[getter]
    fn rotation_second(&self) -> u8 {
        self.inner.key.second_pose.rotation_index
    }

    #[getter]
    fn overlap_area_mm2(&self) -> f64 {
        self.inner.area_mm2
    }

    #[getter]
    fn candidate_digest(&self) -> &str {
        &self.inner.candidate_digest
    }
}

#[cfg(feature = "python")]
#[pymethods]
impl PyCheckpoint {
    #[getter]
    fn max_rounds(&self) -> u32 {
        self.inner.state.limits.max_rounds
    }

    #[getter]
    fn round_budget_ms(&self) -> u64 {
        self.inner.state.limits.round_budget_ms
    }

    #[getter]
    fn terminal_kind(&self) -> Option<&'static str> {
        self.inner.terminal.as_ref().map(|terminal| match terminal {
            TerminalVerdict::Accepted { .. } => "accepted",
            TerminalVerdict::VerifierRejected { .. } => "verifier_rejected",
            TerminalVerdict::NoProgress { .. } => "no_progress",
            TerminalVerdict::RoundLimit { .. } => "round_limit",
            TerminalVerdict::InvalidExperiment { .. } => "invalid_experiment",
        })
    }

    #[getter]
    fn terminal_reason(&self) -> Option<&str> {
        self.inner
            .terminal
            .as_ref()
            .and_then(|terminal| match terminal {
                TerminalVerdict::VerifierRejected { reason }
                | TerminalVerdict::InvalidExperiment { reason } => Some(reason.as_str()),
                _ => None,
            })
    }

    #[staticmethod]
    fn from_bytes(bytes: Vec<u8>) -> PyResult<Self> {
        CampaignCheckpoint::from_bytes(&bytes)
            .map(|inner| Self { inner })
            .map_err(campaign_error)
    }

    fn to_bytes(&self) -> PyResult<Vec<u8>> {
        self.inner.to_bytes().map_err(campaign_error)
    }

    #[pyo3(signature = (board, rules, solver, axis))]
    fn validate_for(
        &self,
        board: String,
        rules: String,
        solver: String,
        axis: String,
    ) -> PyResult<()> {
        let identity =
            InputIdentity::new(&board, &rules, &solver, &axis).map_err(campaign_error)?;
        self.inner
            .validate_identity(&identity)
            .map_err(campaign_error)
    }

    #[pyo3(signature = (board, rules, solver, axis))]
    fn restore_for(
        &self,
        py: Python<'_>,
        board: String,
        rules: String,
        solver: String,
        axis: String,
    ) -> PyResult<Py<PyPrepared>> {
        let identity =
            InputIdentity::new(&board, &rules, &solver, &axis).map_err(campaign_error)?;
        let prepared = self.inner.restore_for(&identity).map_err(campaign_error)?;
        Py::new(
            py,
            PyPrepared {
                inner: Some(prepared),
            },
        )
    }
}
