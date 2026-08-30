//! Valid-state core for bounded collision-aware placement campaigns.
//!
//! Each public transition consumes its phase.  Consequently a terminal
//! verdict cannot be resumed and a candidate cannot be audited twice in
//! safe Rust.  Primitive parsing is confined to validated constructors.

use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet};
use std::fmt;
use temper_geometry::rotation_quadrant::RotationQuadrant;

const CHECKPOINT_MAGIC: &[u8; 8] = b"TCAMP001";
pub const MODEL_UNITS_PER_MM: i64 = 1_000;

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
        if !area_mm2.is_finite() || area_mm2 < 0.0 {
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
        [&self.creepage, &self.body, &self.provenance]
            .into_iter()
            .find_map(|g| match g {
                GateOutcome::Rejected(reason) => Some(reason.clone()),
                _ => None,
            })
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
        }
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
        let mut state = self.state;
        let mut added = 0;
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
            if let Some(existing) = state.cuts.iter().find(|cut| cut.key == key) {
                if existing.area_mm2.to_bits() == witness.area_mm2.to_bits()
                    && existing.candidate_digest == witness.candidate_digest
                {
                    continue;
                }
                return Err(CampaignError::ConflictingCut);
            }
            state.cuts.push(StoredCut {
                key,
                area_mm2: witness.area_mm2,
                candidate_digest: witness.candidate_digest,
            });
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
        self.state
            .cuts
            .iter()
            .map(|c| CollisionCut {
                key: c.key.clone(),
                area_mm2: c.area_mm2,
                candidate_digest: c.candidate_digest.clone(),
            })
            .collect()
    }
    pub fn next_round(self) -> Result<Solving, CampaignError> {
        Ok(Solving { state: self.state })
    }
    pub fn checkpoint(&self) -> CampaignCheckpoint {
        CampaignCheckpoint {
            state: self.state.clone(),
        }
    }
}

#[derive(Debug)]
pub enum AuditDecision {
    Refining(Refining),
    Terminal(TerminalVerdict),
}

#[derive(Debug, Clone, PartialEq, Eq)]
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

#[derive(Debug, Clone)]
pub struct CampaignCheckpoint {
    state: CampaignState,
}
impl CampaignCheckpoint {
    pub fn to_bytes(&self) -> Result<Vec<u8>, CampaignError> {
        let payload = serde_json::to_vec(&self.state)
            .map_err(|e| CampaignError::Checkpoint(e.to_string()))?;
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
        let state: CampaignState = serde_json::from_slice(&bytes[CHECKPOINT_MAGIC.len()..])
            .map_err(|e| CampaignError::Checkpoint(e.to_string()))?;
        validate_checkpoint_state(&state)?;
        Ok(Self { state })
    }
    pub fn restore_for(&self, identity: &InputIdentity) -> Result<Prepared, CampaignError> {
        if &self.state.identity != identity {
            return Err(CampaignError::ForeignIdentity {
                expected: identity.label(),
                actual: self.state.identity.label(),
            });
        }
        Ok(Prepared {
            state: self.state.clone(),
        })
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
        if cut.key.identity != state.identity
            || !state.components.contains(cut.key.pair.first())
            || !state.components.contains(cut.key.pair.second())
            || !cut.area_mm2.is_finite()
            || cut.area_mm2 < 0.0
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
