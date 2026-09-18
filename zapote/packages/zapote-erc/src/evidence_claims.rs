//! Structured evidence claims and the checks the campaign enforces.
//!
//! **What a pass means.** A clean run reports *"no violations detected by
//! implemented checks"*. It does **not** establish that the derivations are
//! sound in general, and it does not establish that any claim is true. The
//! checks are a floor over the specific failures listed below; they cannot see
//! a wrong inference they were not written for.
//!
//! Checks implemented, each rejecting a failure that was actually observed:
//!
//! 1. **Bounds and conditions.** A value carries whether it is typical, minimum,
//!    maximum, assumed or measured, its structured source condition, and its
//!    exact part. The invalid inference "maximum at 50 A" -> "minimum above
//!    50 A" is rejected, as are bound reversal, silent strengthening, a changed
//!    condition without a declared supported transformation, and a changed part
//!    identity without one.
//! 2. **Evidence resolution.** An evidence reference is a path plus a SHA-256.
//!    It must be well formed, and it is resolved against retained bytes when a
//!    resolver is supplied — a reference to a file that does not exist, or whose
//!    hash does not match, is rejected.
//! 3. **Fault states.** healthy/on, healthy/off, failed-short and failed-open
//!    are different devices. A protection claim must name the device that opens
//!    the path and establish it is intact in that scenario.
//! 4. **Completion history.** Statuses advance one rung at a time from `none`,
//!    and the history must actually exist: a submitted `from` that was never
//!    established is rejected.
//! 5. **Claim origin and dependency structure** (`unsound_claim_structure`).
//!    Every claim declares whether it is a `source`, `assumption`,
//!    `measurement` or `derivation`. A derivation must **name its inputs**.
//!    Duplicate ids, names that resolve to no claim, dependency cycles, and
//!    source/measurement claims with no retained evidence are rejected.
//!
//! Check 5 exists because checks 1 and 4 all compare a claim against a **parent**,
//! so a claim that performed a derivation while declaring no parent was compared
//! against nothing and evaded every one of them. Observed on the AR-BOUNDS
//! attempt: `bank-esr-bank-max` computed `0.4737 ohm / 4` in its own
//! justification while declaring `derived_from: null`, and passed. Linking it to
//! its real parent made the source-condition and part checks fire immediately.
//!
//! **The limit of check 5, stated plainly.** It prevents a *declared* derivation
//! from omitting its parents. It cannot detect a calculation that is declared a
//! `source` (or an `assumption`) instead of a derivation, because deciding that
//! requires the meaning of the prose, not its shape. Neither can it detect a
//! document outside the ledger that restates an `illustrative` entry as a bound:
//! the AR-BOUNDS defect reached the packet that way, and the packet's own table
//! is what carried the upgrade. Closing that needs report-to-ledger consistency —
//! generated tables inheriting evidence strength and conditions from the ledger
//! rather than restating them — with prose upgrades caught in review. Do not read
//! a pass here as covering it.
//!
//! Assertion strength applies to **every** claim, root claims included: a claim
//! asserted as `qualified` must carry resolvable evidence.

use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;

/// What kind of value a claim carries.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ValueKind {
    Typical,
    Minimum,
    Maximum,
    Assumed,
    Measured,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum BoundKind {
    Upper,
    Lower,
    Point,
    Unknown,
}

/// A structured source condition. Compared by value, not by presence.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Condition {
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub current_a: Option<f64>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub temperature_c: Option<f64>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub bias_v: Option<f64>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub waveform: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub note: Option<String>,
}

/// A condition given either as free text or in structured form. Text conditions
/// are compared literally, which still catches a changed numeric value.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(untagged)]
pub enum SourceCondition {
    Text(String),
    Structured(Condition),
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum FaultState {
    HealthyOn,
    HealthyOff,
    FailedShort,
    FailedOpen,
    NotApplicable,
    Unknown,
}

impl FaultState {
    pub fn can_open_path(self) -> bool {
        matches!(self, FaultState::HealthyOn | FaultState::HealthyOff)
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum AssertionStrength {
    Illustrative,
    Qualified,
}

/// Where a claim's value came from. Every claim must declare exactly one.
///
/// Before this existed, the only way to express "this came from something" was
/// `derived_from`, and omitting it was a silent default. That made an undeclared
/// derivation indistinguishable from an independently sourced claim — and
/// because every comparison rule in `unsound_derivations` fires *relative to a
/// parent*, a claim could perform a derivation while declaring no parent and
/// evade all of them. The origin is explicit precisely so that omission is a
/// violation rather than a default.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ClaimOrigin {
    /// The value is read from a retained external document (datasheet,
    /// catalogue, standard, contract).
    Source,
    /// The value is assumed. It is not established by a retained source, and it
    /// must remain identifiable as an assumption.
    Assumption,
    /// The value comes from a retained measurement record.
    Measurement,
    /// The value is computed from one or more other claims in this ledger,
    /// which must be named.
    Derivation,
}

impl ClaimOrigin {
    pub fn label(self) -> &'static str {
        match self {
            ClaimOrigin::Source => "source",
            ClaimOrigin::Assumption => "assumption",
            ClaimOrigin::Measurement => "measurement",
            ClaimOrigin::Derivation => "derivation",
        }
    }
}

/// A retained artifact: where it is, and the SHA-256 of its bytes.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct EvidenceRef {
    pub path: String,
    pub sha256: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Claim {
    pub id: String,
    /// Where this claim's value came from. `None` is a violation, not a
    /// default: see [`unsound_claim_structure`].
    #[serde(default)]
    pub origin: Option<ClaimOrigin>,
    /// The claims this one consumes. Required (non-empty) when `origin` is
    /// `derivation`; must be empty otherwise.
    #[serde(default)]
    pub inputs: Vec<String>,
    pub quantity: String,
    #[serde(default)]
    pub part: Option<String>,
    pub value_kind: ValueKind,
    pub bound_kind: BoundKind,
    #[serde(default)]
    pub source_condition: Option<SourceCondition>,
    pub fault_state: FaultState,
    pub assertion: AssertionStrength,
    /// Retained artifacts supporting the claim. Required when `assertion` is
    /// `qualified`.
    #[serde(default)]
    pub evidence: Vec<EvidenceRef>,
    #[serde(default)]
    pub derived_from: Option<String>,
    /// Required when a derived claim's part differs from its parent's.
    #[serde(default)]
    pub part_transformation: Option<String>,
    /// Required when a derived claim's condition differs from its parent's.
    #[serde(default)]
    pub condition_transformation: Option<String>,
    #[serde(default)]
    pub justification: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProtectionClaim {
    pub case_id: String,
    pub fault_case: FaultState,
    #[serde(default)]
    pub interrupting_device: Option<String>,
    pub interrupting_device_state: FaultState,
    pub interrupts: bool,
    #[serde(default)]
    pub evidence: Vec<EvidenceRef>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum CompletionStatus {
    None,
    ProtectionIdentified,
    PartSelected,
    CoordinationDemonstrated,
    HardwareVerified,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Promotion {
    pub subject: String,
    pub from: CompletionStatus,
    pub to: CompletionStatus,
    #[serde(default)]
    pub evidence: Vec<EvidenceRef>,
}

impl CompletionStatus {
    pub fn rank(self) -> u8 {
        match self {
            CompletionStatus::None => 0,
            CompletionStatus::ProtectionIdentified => 1,
            CompletionStatus::PartSelected => 2,
            CompletionStatus::CoordinationDemonstrated => 3,
            CompletionStatus::HardwareVerified => 4,
        }
    }
}

fn bound_strength(kind: BoundKind) -> u8 {
    match kind {
        BoundKind::Unknown => 0,
        BoundKind::Upper | BoundKind::Lower => 1,
        BoundKind::Point => 2,
    }
}

/// A ledger with nothing in it must not read as a clean pass.
pub fn empty_ledger_failure(
    claim_count: usize,
    protection_count: usize,
    promotion_count: usize,
) -> Option<String> {
    if claim_count + protection_count + promotion_count == 0 {
        Some(
            "ledger contains no claims, protection claims or promotions; \
             a clean pass on nothing is not a pass"
                .into(),
        )
    } else {
        None
    }
}

fn nonempty(value: &Option<String>) -> bool {
    value.as_deref().is_some_and(|v| !v.trim().is_empty())
}

fn is_sha256(value: &str) -> bool {
    value.len() == 64 && value.chars().all(|c| c.is_ascii_hexdigit())
}

/// A claim's declared inputs: `derived_from` plus `inputs`, deduplicated.
pub fn claim_inputs(claim: &Claim) -> Vec<&str> {
    let mut out: Vec<&str> = Vec::new();
    if let Some(parent) = claim.derived_from.as_deref() {
        out.push(parent);
    }
    for input in &claim.inputs {
        if !out.contains(&input.as_str()) {
            out.push(input.as_str());
        }
    }
    out
}

/// One message per structural defect: a claim with no declared origin, a
/// duplicated id, a derivation that names no inputs, a name that resolves to no
/// claim, a dependency cycle, and source/measurement claims with no retained
/// evidence.
///
/// **What this closes.** Every rule in [`unsound_derivations`] compares a claim
/// against a parent, so a claim that performs a derivation while declaring no
/// parent was compared against nothing. Requiring an origin and requiring a
/// derivation to name its inputs makes that omission a violation.
///
/// **What this does not close.** It cannot tell that a claim *labelled* `source`
/// is really a calculation, because deciding that needs the meaning of the prose,
/// not its shape. A calculation can still be declared an assumption and pass. Nor
/// can it see a document that upgrades an entry's strength outside the ledger.
/// See the module documentation.
pub fn unsound_claim_structure(claims: &[Claim]) -> Vec<String> {
    let mut failures = Vec::new();

    // Duplicate ids. The id-keyed lookup below keeps only the last, so a
    // duplicate would silently shadow the earlier claim.
    let mut counts: BTreeMap<&str, usize> = BTreeMap::new();
    for claim in claims {
        *counts.entry(claim.id.as_str()).or_insert(0) += 1;
    }
    for (id, count) in &counts {
        if *count > 1 {
            failures.push(format!(
                "claim id {id} appears {count} times; ids must be unique, or a later claim silently shadows an earlier one"
            ));
        }
    }

    let by_id: BTreeMap<&str, &Claim> = claims.iter().map(|c| (c.id.as_str(), c)).collect();

    for claim in claims {
        let Some(origin) = claim.origin else {
            failures.push(format!(
                "{} declares no origin: every claim must state whether it is a source, assumption, measurement or derivation",
                claim.id
            ));
            continue;
        };

        let inputs = claim_inputs(claim);

        // Origin and topology must agree, in both directions.
        if origin == ClaimOrigin::Derivation && inputs.is_empty() {
            failures.push(format!(
                "{} is declared a derivation but names no inputs; a derivation must name what it derives from",
                claim.id
            ));
        }
        if origin != ClaimOrigin::Derivation && !inputs.is_empty() {
            failures.push(format!(
                "{} declares inputs ({}) but its origin is {}; a claim that consumes other claims is a derivation",
                claim.id,
                inputs.join(", "),
                origin.label()
            ));
        }

        // Named inputs must resolve. `derived_from` is also reported by
        // `unsound_derivations`; report each name once.
        for input in claim_inputs(claim) {
            if input == claim.id {
                failures.push(format!("{} names itself as an input", claim.id));
            } else if !by_id.contains_key(input) {
                failures.push(format!(
                    "{} names input {input}, which is not among the claims",
                    claim.id
                ));
            }
        }

        // A source or a measurement must point at retained bytes.
        if matches!(origin, ClaimOrigin::Source | ClaimOrigin::Measurement)
            && claim.evidence.is_empty()
        {
            failures.push(format!(
                "{} is declared a {} but references no retained evidence",
                claim.id,
                origin.label()
            ));
        }
    }

    // Dependency cycles: a derivation that consumes itself, directly or
    // transitively, has no base case.
    let edges: BTreeMap<&str, Vec<&str>> = claims
        .iter()
        .map(|c| (c.id.as_str(), claim_inputs(c)))
        .collect();
    let mut state: BTreeMap<&str, u8> = BTreeMap::new();
    let mut stack: Vec<&str> = Vec::new();
    let mut seen_cycles: Vec<String> = Vec::new();
    for claim in claims {
        visit_for_cycles(
            claim.id.as_str(),
            &edges,
            &mut state,
            &mut stack,
            &mut seen_cycles,
        );
    }
    failures.extend(seen_cycles);

    failures
}

fn visit_for_cycles<'a>(
    node: &'a str,
    edges: &BTreeMap<&'a str, Vec<&'a str>>,
    state: &mut BTreeMap<&'a str, u8>,
    stack: &mut Vec<&'a str>,
    failures: &mut Vec<String>,
) {
    match state.get(node) {
        Some(2) => return,
        Some(1) => return, // already on the stack; the cycle is reported by its opener
        _ => {}
    }
    state.insert(node, 1);
    stack.push(node);

    for child in edges.get(node).into_iter().flatten() {
        if !edges.contains_key(child) {
            continue; // unresolved name; reported above
        }
        match state.get(child) {
            Some(1) => {
                let from = stack.iter().position(|n| n == child).unwrap_or(0);
                let mut path: Vec<&str> = stack[from..].to_vec();
                path.push(child);
                let message = format!("dependency cycle: {}", path.join(" -> "));
                if !failures.contains(&message) {
                    failures.push(message);
                }
            }
            Some(2) => {}
            _ => visit_for_cycles(child, edges, state, stack, failures),
        }
    }

    stack.pop();
    state.insert(node, 2);
}

/// One message per derivation that changes a load-bearing property without a
/// declared supported transformation. Applies to root claims too.
pub fn unsound_derivations(claims: &[Claim]) -> Vec<String> {
    let by_id: BTreeMap<&str, &Claim> = claims.iter().map(|c| (c.id.as_str(), c)).collect();
    let mut failures = Vec::new();

    for claim in claims {
        // Assertion strength applies to every claim, root claims included.
        if claim.assertion == AssertionStrength::Qualified && claim.evidence.is_empty() {
            failures.push(format!(
                "{} is asserted as qualified with no evidence reference",
                claim.id
            ));
        }

        // The comparison parent: `derived_from` when present, else the first
        // declared input. This keeps the comparison rules firing against
        // something for a derivation that names inputs but no `derived_from`.
        let Some(parent_id) = claim_inputs(claim).into_iter().next() else {
            continue;
        };
        let Some(parent) = by_id.get(parent_id) else {
            continue; // unresolved name; reported by unsound_claim_structure
        };

        // Bound direction.
        let reversed = matches!(
            (parent.bound_kind, claim.bound_kind),
            (BoundKind::Upper, BoundKind::Lower) | (BoundKind::Lower, BoundKind::Upper)
        );
        if reversed {
            failures.push(format!(
                "{} reverses the bound direction of {}: {:?} -> {:?}",
                claim.id, parent.id, parent.bound_kind, claim.bound_kind
            ));
        } else if bound_strength(claim.bound_kind) > bound_strength(parent.bound_kind)
            && !nonempty(&claim.justification)
        {
            failures.push(format!(
                "{} strengthens {} ({:?} -> {:?}) with no justification",
                claim.id, parent.id, parent.bound_kind, claim.bound_kind
            ));
        }

        // The specific invalid inference.
        if matches!(
            (parent.value_kind, claim.value_kind),
            (ValueKind::Maximum, ValueKind::Minimum) | (ValueKind::Minimum, ValueKind::Maximum)
        ) {
            failures.push(format!(
                "{} restates {}'s {:?} as a {:?} — a bound cannot flip direction",
                claim.id, parent.id, parent.value_kind, claim.value_kind
            ));
        }

        if matches!(
            (parent.value_kind, claim.value_kind),
            (ValueKind::Assumed, ValueKind::Measured) | (ValueKind::Typical, ValueKind::Measured)
        ) && !nonempty(&claim.justification)
        {
            failures.push(format!(
                "{} promotes {}'s {:?} to {:?} with no justification",
                claim.id, parent.id, parent.value_kind, claim.value_kind
            ));
        }

        // Source condition: carried, and unchanged without a declared transformation.
        match (&parent.source_condition, &claim.source_condition) {
            (Some(_), None) => failures.push(format!(
                "{} drops the source condition of {}",
                claim.id, parent.id
            )),
            (Some(a), Some(b)) if a != b && !nonempty(&claim.condition_transformation) => {
                failures.push(format!(
                    "{} changes {}'s source condition with no supported transformation",
                    claim.id, parent.id
                ));
            }
            _ => {}
        }

        // Part identity: carried, and unchanged without a declared transformation.
        match (&parent.part, &claim.part) {
            (Some(_), None) => failures.push(format!(
                "{} drops the part binding of {}",
                claim.id, parent.id
            )),
            (Some(a), Some(b)) if a != b && !nonempty(&claim.part_transformation) => {
                failures.push(format!(
                    "{} changes {}'s part ({a} -> {b}) with no supported transformation",
                    claim.id, parent.id
                ));
            }
            _ => {}
        }

        // Fault state.
        if parent.fault_state != claim.fault_state && !nonempty(&claim.justification) {
            failures.push(format!(
                "{} changes fault state from {} ({:?} -> {:?}) with no justification",
                claim.id, parent.id, parent.fault_state, claim.fault_state
            ));
        }

        // Illustrative -> qualified needs resolvable evidence.
        if parent.assertion == AssertionStrength::Illustrative
            && claim.assertion == AssertionStrength::Qualified
            && claim.evidence.is_empty()
        {
            failures.push(format!(
                "{} promotes {}'s illustrative result to a qualified prediction with no evidence",
                claim.id, parent.id
            ));
        }
    }
    failures
}

/// Every evidence reference in a ledger, with its owner.
///
/// One validation path covers claims, protection claims and promotions alike: an
/// evidence reference is an evidence reference wherever it appears, and a
/// collection that merely requires a *non-empty* list is not checking anything.
pub fn ledger_evidence<'a>(
    claims: &'a [Claim],
    protection_claims: &'a [ProtectionClaim],
    promotions: &'a [Promotion],
) -> Vec<(String, &'a [EvidenceRef])> {
    let mut owners: Vec<(String, &'a [EvidenceRef])> = Vec::new();
    for claim in claims {
        owners.push((format!("claim {}", claim.id), &claim.evidence));
    }
    for claim in protection_claims {
        owners.push((format!("protection claim {}", claim.case_id), &claim.evidence));
    }
    for promotion in promotions {
        owners.push((
            format!("promotion {} -> {:?}", promotion.subject, promotion.to),
            &promotion.evidence,
        ));
    }
    owners
}

/// One message per evidence reference that is malformed or does not resolve,
/// across every collection that carries evidence.
///
/// `resolve` maps a path to the SHA-256 of the retained bytes, or `None` when
/// nothing is retained at that path. Pass a filesystem-backed resolver to check
/// real artifacts; pass `|_| None` to skip resolution and check form only.
pub fn unsound_evidence<'a, I, R>(owners: I, resolve: R) -> Vec<String>
where
    I: IntoIterator<Item = (String, &'a [EvidenceRef])>,
    R: Fn(&str) -> Option<String>,
{
    let mut failures = Vec::new();
    for (owner, refs) in owners {
        for reference in refs {
            if reference.path.trim().is_empty() {
                failures.push(format!("{owner} has an evidence reference with no path"));
            }
            if !is_sha256(&reference.sha256) {
                failures.push(format!(
                    "{owner} references {} with a malformed sha256 {:?}",
                    reference.path, reference.sha256
                ));
                continue;
            }
            match resolve(&reference.path) {
                None => failures.push(format!(
                    "{owner} references {} which is not retained",
                    reference.path
                )),
                Some(actual) if actual != reference.sha256 => failures.push(format!(
                    "{owner} references {} whose bytes hash {actual}, not {}",
                    reference.path, reference.sha256
                )),
                Some(_) => {}
            }
        }
    }
    failures
}

/// One message per protection claim that credits an interruption it cannot support.
pub fn unsound_protection_claims(claims: &[ProtectionClaim]) -> Vec<String> {
    let mut failures = Vec::new();
    for claim in claims {
        if !claim.interrupts {
            continue;
        }
        let Some(device) = claim.interrupting_device.as_deref() else {
            failures.push(format!(
                "{} claims interruption without naming the device that opens the path",
                claim.case_id
            ));
            continue;
        };
        if !claim.interrupting_device_state.can_open_path() {
            failures.push(format!(
                "{} credits {device} with interruption while it is {:?}; only an intact device can open a path",
                claim.case_id, claim.interrupting_device_state
            ));
        }
        if claim.evidence.is_empty() {
            failures.push(format!(
                "{} claims {device} interrupts with no retained evidence",
                claim.case_id
            ));
        }
    }
    failures
}

/// One message per promotion that skips a rung, lacks evidence, or claims a
/// `from` status that the history never established.
pub fn unsound_promotions(promotions: &[Promotion]) -> Vec<String> {
    let mut failures = Vec::new();
    let mut by_subject: BTreeMap<&str, Vec<&Promotion>> = BTreeMap::new();
    for promotion in promotions {
        by_subject.entry(promotion.subject.as_str()).or_default().push(promotion);
    }

    for (subject, mut steps) in by_subject {
        steps.sort_by_key(|p| p.to.rank());
        let mut established = 0u8;
        for step in steps {
            if step.to.rank() != established + 1 {
                failures.push(format!(
                    "{subject} promotes to {:?} while the established status is rank {established}; the history does not support {:?} -> {:?}",
                    step.to, step.from, step.to
                ));            }
            if step.from.rank() != established {
                failures.push(format!(
                    "{subject} claims to promote from {:?}, which the recorded history does not establish",
                    step.from
                ));
            }
            if step.evidence.is_empty() {
                failures.push(format!("{subject} promotes to {:?} with no evidence", step.to));
            }
            established = step.to.rank();
        }
    }
    failures
}

#[cfg(test)]
mod tests {
    use super::*;

    fn evidence_failures(
        claims: &[Claim],
        protection: &[ProtectionClaim],
        promotions: &[Promotion],
        resolve: impl Fn(&str) -> Option<String>,
    ) -> Vec<String> {
        unsound_evidence(ledger_evidence(claims, protection, promotions), resolve)
    }

    /// A real retained artifact in a temporary directory, with its true SHA-256.
    fn temp_artifact(name: &str, bytes: &[u8]) -> (std::path::PathBuf, String) {
        use sha2::{Digest, Sha256};
        let dir = std::env::temp_dir().join(format!("zapote-claims-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let path = dir.join(name);
        std::fs::write(&path, bytes).unwrap();
        let mut hasher = Sha256::new();
        hasher.update(bytes);
        (path, format!("{:x}", hasher.finalize()))
    }

    fn file_resolver() -> impl Fn(&str) -> Option<String> {
        |path: &str| {
            use sha2::{Digest, Sha256};
            let bytes = std::fs::read(path).ok()?;
            let mut hasher = Sha256::new();
            hasher.update(&bytes);
            Some(format!("{:x}", hasher.finalize()))
        }
    }

    fn ref_to(path: &std::path::Path, sha: &str) -> EvidenceRef {
        EvidenceRef { path: path.to_string_lossy().into_owned(), sha256: sha.to_string() }
    }

    fn protection_with(evidence: Vec<EvidenceRef>) -> ProtectionClaim {
        ProtectionClaim {
            case_id: "short".into(),
            fault_case: FaultState::FailedShort,
            interrupting_device: Some("Fbus".into()),
            interrupting_device_state: FaultState::HealthyOn,
            interrupts: true,
            evidence,
        }
    }

    fn promotion_with(evidence: Vec<EvidenceRef>) -> Promotion {
        Promotion {
            subject: "bus protection".into(),
            from: CompletionStatus::None,
            to: CompletionStatus::ProtectionIdentified,
            evidence,
        }
    }

    fn cond(amps: f64) -> Option<SourceCondition> {
        Some(SourceCondition::Text(format!("{amps} A, 8/20 us, 25 C")))
    }

    fn evidence(path: &str) -> EvidenceRef {
        EvidenceRef { path: path.into(), sha256: "a".repeat(64) }
    }

    fn root() -> Claim {
        Claim {
            id: "source".into(),
            origin: Some(ClaimOrigin::Assumption),
            inputs: Vec::new(),
            quantity: "clamp_voltage".into(),
            part: Some("V150LA10AP".into()),
            value_kind: ValueKind::Maximum,
            bound_kind: BoundKind::Upper,
            source_condition: cond(50.0),
            fault_state: FaultState::NotApplicable,
            assertion: AssertionStrength::Illustrative,
            evidence: Vec::new(),
            derived_from: None,
            part_transformation: None,
            condition_transformation: None,
            justification: None,
        }
    }

    fn child() -> Claim {
        Claim {
            id: "child".into(),
            origin: Some(ClaimOrigin::Derivation),
            inputs: vec!["source".into()],
            derived_from: Some("source".into()),
            ..root()
        }
    }

    // ---- claim origin and dependency structure ----

    /// The AR-BOUNDS defect, reduced: a claim whose justification performs a
    /// derivation but which names no parent must be rejected.
    #[test]
    fn a_derivation_that_names_no_inputs_is_rejected() {
        let mut c = child();
        c.derived_from = None;
        c.inputs.clear();
        let out = unsound_claim_structure(&[root(), c]);
        assert!(
            out.iter().any(|f| f.contains("declared a derivation but names no inputs")),
            "{out:?}"
        );
    }

    #[test]
    fn a_claim_with_no_declared_origin_is_rejected() {
        let mut r = root();
        r.origin = None;
        let out = unsound_claim_structure(&[r]);
        assert!(out.iter().any(|f| f.contains("declares no origin")), "{out:?}");
    }

    #[test]
    fn duplicate_claim_ids_are_rejected() {
        let out = unsound_claim_structure(&[root(), root()]);
        assert!(out.iter().any(|f| f.contains("appears 2 times")), "{out:?}");
    }

    #[test]
    fn an_input_that_names_no_claim_is_rejected() {
        let mut c = child();
        c.inputs = vec!["nonexistent".into()];
        c.derived_from = None;
        let out = unsound_claim_structure(&[root(), c]);
        assert!(
            out.iter().any(|f| f.contains("names input nonexistent") && f.contains("not among the claims")),
            "{out:?}"
        );
    }

    #[test]
    fn a_dependency_cycle_is_rejected() {
        let mut a = child();
        a.id = "a".into();
        a.inputs = vec!["b".into()];
        a.derived_from = None;
        let mut b = child();
        b.id = "b".into();
        b.inputs = vec!["a".into()];
        b.derived_from = None;
        let out = unsound_claim_structure(&[a, b]);
        assert!(out.iter().any(|f| f.contains("dependency cycle")), "{out:?}");
    }

    #[test]
    fn a_source_claim_with_no_retained_evidence_is_rejected() {
        let mut r = root();
        r.origin = Some(ClaimOrigin::Source);
        r.evidence = Vec::new();
        let out = unsound_claim_structure(&[r]);
        assert!(
            out.iter().any(|f| f.contains("declared a source but references no retained evidence")),
            "{out:?}"
        );
    }

    #[test]
    fn a_measurement_claim_with_no_retained_evidence_is_rejected() {
        let mut r = root();
        r.origin = Some(ClaimOrigin::Measurement);
        r.evidence = Vec::new();
        let out = unsound_claim_structure(&[r]);
        assert!(
            out.iter().any(|f| f.contains("declared a measurement but references no retained evidence")),
            "{out:?}"
        );
    }

    #[test]
    fn a_non_derivation_declaring_inputs_is_rejected() {
        let mut r = root();
        r.origin = Some(ClaimOrigin::Assumption);
        r.inputs = vec!["something".into()];
        let out = unsound_claim_structure(&[root(), r]);
        assert!(
            out.iter().any(|f| f.contains("but its origin is assumption")),
            "{out:?}"
        );
    }

    #[test]
    fn a_claim_naming_itself_is_rejected() {
        let mut c = child();
        c.inputs = vec!["child".into()];
        c.derived_from = None;
        let out = unsound_claim_structure(&[root(), c]);
        assert!(out.iter().any(|f| f.contains("names itself as an input")), "{out:?}");
    }

    /// The legitimate roots and derivations must still pass, so the structure
    /// checks cannot be satisfied by rejecting everything.
    #[test]
    fn declared_origins_and_a_resolved_dependency_are_allowed() {
        let mut source = root();
        source.id = "datasheet".into();
        source.origin = Some(ClaimOrigin::Source);
        source.evidence = vec![evidence("datasheet.pdf")];

        let mut assumption = root();
        assumption.id = "model".into();
        assumption.origin = Some(ClaimOrigin::Assumption);

        let mut measurement = root();
        measurement.id = "bench".into();
        measurement.origin = Some(ClaimOrigin::Measurement);
        measurement.evidence = vec![evidence("bench-run.json")];

        let mut derivation = child();
        derivation.id = "derived".into();
        derivation.inputs = vec!["datasheet".into(), "model".into()];
        derivation.derived_from = Some("datasheet".into());

        let out = unsound_claim_structure(&[source, assumption, measurement, derivation]);
        assert!(out.is_empty(), "{out:?}");
    }

    /// A derivation that names its inputs through `inputs` alone (no
    /// `derived_from`) is still compared against a parent, so the existing
    /// comparison rules cannot be evaded by using only the input list.
    #[test]
    fn inputs_alone_still_drive_the_comparison_rules() {
        let mut parent = root();
        parent.id = "p".into();
        parent.origin = Some(ClaimOrigin::Assumption);

        let mut c = child();
        c.id = "c".into();
        c.inputs = vec!["p".into()];
        c.derived_from = None;
        c.source_condition = cond(500.0); // changed, with no transformation

        let out = unsound_derivations(&[parent, c]);
        assert!(
            out.iter().any(|f| f.contains("changes") && f.contains("source condition")),
            "{out:?}"
        );
    }

    // ---- the six probe inputs, as regressions ----

    #[test]
    fn changing_50a_to_500a_without_a_transformation_is_rejected() {
        let mut c = child();
        c.source_condition = cond(500.0);
        let out = unsound_derivations(&[root(), c]);
        assert!(out.iter().any(|f| f.contains("changes") && f.contains("source condition")), "{out:?}");
    }

    #[test]
    fn changing_the_part_without_a_transformation_is_rejected() {
        let mut c = child();
        c.part = Some("DIFFERENT_PART".into());
        let out = unsound_derivations(&[root(), c]);
        assert!(out.iter().any(|f| f.contains("changes") && f.contains("part")), "{out:?}");
    }

    #[test]
    fn a_root_claim_qualified_without_evidence_is_rejected() {
        let mut r = root();
        r.assertion = AssertionStrength::Qualified;
        let out = unsound_derivations(&[r]);
        assert!(out.iter().any(|f| f.contains("qualified with no evidence")), "{out:?}");
    }

    #[test]
    fn a_nonexistent_evidence_file_is_rejected() {
        let mut c = child();
        c.assertion = AssertionStrength::Qualified;
        c.evidence = vec![evidence("/does-not-exist/review.pdf")];
        let out = evidence_failures(&[c], &[], &[], |_| None);
        assert!(out.iter().any(|f| f.contains("not retained")), "{out:?}");
    }

    #[test]
    fn evidence_whose_bytes_do_not_match_its_hash_is_rejected() {
        let mut c = child();
        c.assertion = AssertionStrength::Qualified;
        c.evidence = vec![evidence("review.pdf")];
        let out = evidence_failures(&[c], &[], &[], |_| Some("b".repeat(64)));
        assert!(out.iter().any(|f| f.contains("whose bytes hash")), "{out:?}");
    }

    #[test]
    fn an_unsupported_completion_history_is_rejected() {
        let promotion = Promotion {
            subject: "protection".into(),
            from: CompletionStatus::CoordinationDemonstrated,
            to: CompletionStatus::HardwareVerified,
            evidence: vec![evidence("/does-not-exist/bench-record.pdf")],
        };
        let out = unsound_promotions(&[promotion]);
        assert!(out.iter().any(|f| f.contains("history does not establish") || f.contains("does not establish")), "{out:?}");
    }

    // ---- valid counterexamples ----

    #[test]
    fn a_declared_part_transformation_is_allowed() {
        let mut c = child();
        c.part = Some("ALTERNATE".into());
        c.part_transformation = Some("superseded part, same die, see PCN".into());
        assert!(unsound_derivations(&[root(), c]).is_empty());
    }

    #[test]
    fn a_declared_condition_transformation_is_allowed() {
        let mut c = child();
        c.source_condition = cond(500.0);
        c.condition_transformation = Some("digitised V-I curve at 500 A, per Figure 10".into());
        assert!(unsound_derivations(&[root(), c]).is_empty());
    }

    #[test]
    fn resolving_evidence_is_allowed() {
        let mut c = child();
        c.assertion = AssertionStrength::Qualified;
        c.evidence = vec![evidence("review.pdf")];
        assert!(evidence_failures(&[c], &[], &[], |_| Some("a".repeat(64))).is_empty());
    }

    #[test]
    fn a_full_completion_chain_is_allowed() {
        let step = |from, to| Promotion {
            subject: "protection".into(),
            from,
            to,
            evidence: vec![evidence("evidence.pdf")],
        };
        let out = unsound_promotions(&[
            step(CompletionStatus::None, CompletionStatus::ProtectionIdentified),
            step(CompletionStatus::ProtectionIdentified, CompletionStatus::PartSelected),
            step(CompletionStatus::PartSelected, CompletionStatus::CoordinationDemonstrated),
        ]);
        assert!(out.is_empty(), "{out:?}");
    }

    #[test]
    fn a_declared_non_interruption_needs_nothing() {
        let claim = ProtectionClaim {
            case_id: "case".into(),
            fault_case: FaultState::FailedShort,
            interrupting_device: None,
            interrupting_device_state: FaultState::FailedShort,
            interrupts: false,
            evidence: Vec::new(),
        };
        assert!(unsound_protection_claims(&[claim]).is_empty());
    }

    // --- one shared evidence path across all three collections ---

    #[test]
    fn a_protection_claim_citing_a_nonexistent_file_is_rejected() {
        let claim = protection_with(vec![EvidenceRef {
            path: "missing-evidence.pdf".into(),
            sha256: "a".repeat(64),
        }]);
        let out = evidence_failures(&[], &[claim], &[], |_| None);
        assert!(
            out.iter().any(|f| f.starts_with("protection claim short") && f.contains("not retained")),
            "{out:?}"
        );
    }

    #[test]
    fn a_promotion_citing_a_nonexistent_file_is_rejected() {
        let out = evidence_failures(
            &[],
            &[],
            &[promotion_with(vec![EvidenceRef {
                path: "missing-evidence.pdf".into(),
                sha256: "a".repeat(64),
            }])],
            |_| None,
        );
        assert!(
            out.iter().any(|f| f.starts_with("promotion bus protection") && f.contains("not retained")),
            "{out:?}"
        );
    }

    #[test]
    fn a_valid_retained_file_passes_in_every_collection() {
        let (path, digest) = temp_artifact("shared.pdf", b"shared retained evidence");
        let reference = ref_to(&path, &digest);
        let mut claim = child();
        claim.assertion = AssertionStrength::Qualified;
        claim.evidence = vec![reference.clone()];
        let out = evidence_failures(
            &[claim],
            &[protection_with(vec![reference.clone()])],
            &[promotion_with(vec![reference])],
            file_resolver(),
        );
        assert!(out.is_empty(), "{out:?}");
    }

    #[test]
    fn a_hash_mismatch_is_rejected_in_every_collection() {
        let (path, digest) = temp_artifact("mismatch.pdf", b"real bytes");
        let wrong = "0".repeat(64);
        assert_ne!(digest, wrong);
        let reference = ref_to(&path, &wrong);
        let mut claim = child();
        claim.assertion = AssertionStrength::Qualified;
        claim.evidence = vec![reference.clone()];
        let out = evidence_failures(
            &[claim],
            &[protection_with(vec![reference.clone()])],
            &[promotion_with(vec![reference])],
            file_resolver(),
        );
        assert_eq!(
            out.iter().filter(|f| f.contains("whose bytes hash")).count(),
            3,
            "{out:?}"
        );
    }

    #[test]
    fn a_missing_file_is_rejected_in_every_collection() {
        let reference = EvidenceRef { path: "nope.pdf".into(), sha256: "a".repeat(64) };
        let mut claim = child();
        claim.assertion = AssertionStrength::Qualified;
        claim.evidence = vec![reference.clone()];
        let out = evidence_failures(
            &[claim],
            &[protection_with(vec![reference.clone()])],
            &[promotion_with(vec![reference])],
            |_| None,
        );
        assert_eq!(out.iter().filter(|f| f.contains("not retained")).count(), 3, "{out:?}");
    }
}
