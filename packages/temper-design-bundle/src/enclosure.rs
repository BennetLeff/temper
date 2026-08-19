//! Enclosure declaration -> pollution degree -> reinforced HV<->SELV creepage.
//!
//! ## What this module is for
//!
//! The board's pollution-degree classification sets the reinforced HV<->SELV
//! creepage requirement -- the single most consequential safety number in
//! this design. Until this module existed that number was a **literal**
//! (`MIN_BARRIER_WIDTH_MM = 12.6` in
//! `packages/temper-placer/src/temper_placer/core/isolation_constants.py`),
//! with the alternative (8.0 mm, PD2) in a docstring, and the rationale in an
//! evidence document that can go stale. Three structural gaps followed:
//!
//! 1. **Nothing connected them.** Every investigation re-derived the
//!    reasoning, and some got it wrong.
//! 2. **The stated precondition was unverifiable.** The docstring's *"sealed,
//!    gasketed PCB compartment ... verified before release"* had no mechanism
//!    behind it.
//! 3. **The physical state and the number could drift silently in both
//!    directions.** Build the compartment, nothing loosened; remove it,
//!    nothing re-tightened.
//!
//! This module closes (1) and (3) by making the number a **function of a
//! declared, dated, commit-anchored physical claim**, evaluated through the
//! already-recovered IEC 60335-1 tables in [`crate::safety_value`]. The
//! companion gate (`scripts/check_enclosure_declaration.py`) closes (2) as
//! far as software can.
//!
//! ## What this module CANNOT do -- state this every time it is quoted
//!
//! **No gate makes a physical enclosure real.** Everything here operates on a
//! *claim*. This module can ensure the claim is explicit, internally
//! consistent, anchored to a resolvable commit, and not silently edited after
//! the verification that backs it -- and it can make the safety number move
//! in lockstep with the claim. It cannot observe a gasket. Sealing is a
//! manufacturing and QA matter; see [`LIMITATION`], which the gate prints on
//! every run so the assurance this provides is never overstated.
//!
//! ## The derivation chain
//!
//! ```text
//! elec/enclosure_manifest.yaml   (declared physical facts + verification)
//!   -> EnclosureFacts
//!   -> pollution_degree_for()    (IEC 60335-2-6 cl. 29.2 Addition, as
//!                                 determined by this repo's own evidence)
//!   -> table_17_lookup(pd, IIIa/IIIb, >250-400 V)   (recovered Table 17)
//!   -> creepage_reinforced()     (cl. 29.2.3: reinforced = 2 x basic)
//!   -> MIN_BARRIER_WIDTH_MM
//! ```
//!
//! Today that chain evaluates to **PD3 -> 6.3 mm basic -> 12.6 mm
//! reinforced**, which is exactly the figure that was previously written as a
//! literal. Nothing about the enforced classification changes here; what
//! changes is that it is now *derived* and *checked* rather than *asserted*.
//!
//! ## Why PD2 is a conditional exception and PD3 the default
//!
//! Not invented here, and not reconstructed from a paywalled text. This is
//! the determination this repository already made and documented against the
//! primary sources it holds:
//!
//! * [`DOC_PD3_DECISION`] -- the 2026-08-15 data-driven decision: *"the
//!   board is forced-air vented with no cover/gasket/partition"*, so PD3
//!   governs the as-built board; enforcing PD2 was unearned credit.
//! * [`DOC_PD2_LEGITIMACY`] -- the PD2 exception (IEC 60335-2-6 cl. 29.2
//!   Addition) and the sealed-compartment prerequisite it is conditional on.
//! * [`DOC_PD2_DECISION_RECORD`] -- the record of the intent to build that
//!   compartment, and the accounting of why it does not exist today.
//!
//! IEC 60664-1 Annex L and IEC 60664-4 are paywalled and **not obtainable**
//! in this repository; nothing here depends on them.
//!
//! ## Design notes
//!
//! * [`pollution_degree_for`] is **total and conservative by construction**:
//!   it returns [`PollutionDegree::PD2`] only when every one of the declared
//!   preconditions holds, and [`PollutionDegree::PD3`] in every other case.
//!   There is no input that yields a value looser than PD3 by accident. It is
//!   exhaustively tested over all 2^3 fact combinations.
//! * **PD1 is not reachable from this rule at all.** PD1 requires a
//!   qualified conformal coating or hermetic sealing, which is a *different*
//!   claim gated separately (`COATING_QUALIFIED` in
//!   `scripts/generate_kicad_dru.py`, and
//!   `docs/evidence/2026-07-28-conformal-coating-pd1.md`, which measured
//!   that 100 % of the shortest HV<->PELV surface path on this board lies
//!   under a component body). Declaring a sealed compartment must never
//!   silently buy PD1.
//! * **The declaration's own integrity is checked before the rule runs.**
//!   [`resolve`] refuses a declaration whose `verification.declared_state_sha256`
//!   does not match the digest of the `enclosure:` block it accompanies --
//!   i.e. someone edited the physical claim without re-verifying it. This is
//!   the same "content hash is the primary identity" rule
//!   `scripts/check_measurement_provenance.py` already applies to
//!   `drc_ceiling.json`, reused rather than reinvented.
//! * **`evidence_resolved` is an input, not something this module assumes.**
//!   The caller must prove the verification commit resolves in the local
//!   object store. A PD2-qualifying declaration whose evidence does not
//!   resolve is a hard [`DeclarationError::UnresolvableVerificationCommit`],
//!   not a silent downgrade to PD3 -- a dangling anchor claims traceability
//!   it does not have while looking exactly like one that does. The ceiling
//!   corpus is the cautionary tale: its "fully-evidenced" control used
//!   `measured_at_commit = "0" * 40`, the ratchet rejected it as
//!   unresolvable, and the control silently never ran for months.
//! * **No pyo3 in the core.** The types and the rule compile under
//!   `--no-default-features` and onto the `wasm32` tier; the pyo3 surface is
//!   `#[cfg(feature = "python")]`-gated at the bottom of the file.

use serde::Deserialize;
use sha2::{Digest, Sha256};

use crate::safety_value::{
    creepage_reinforced, table_17_lookup, MaterialGroup, PollutionDegree, SafetyValue, VoltageRange,
};

// ---------------------------------------------------------------------------
// Evidence documents (the determination this rule encodes)
// ---------------------------------------------------------------------------

/// The 2026-08-15 data-driven decision that PD3 governs the as-built board.
pub const DOC_PD3_DECISION: &str = "docs/evidence/2026-08-15-pd2-pd3-data-driven-decision.md";

/// The PD2 exception's legitimacy analysis and its sealed-compartment
/// prerequisite (IEC 60335-2-6 cl. 29.2 Addition).
pub const DOC_PD2_LEGITIMACY: &str = "docs/evidence/2026-08-01-pd2-enclosure-legitimacy.md";

/// The record of the (unbuilt) sealed-compartment intent.
pub const DOC_PD2_DECISION_RECORD: &str = "docs/evidence/2026-08-11-pd2-decision-record.md";

/// The honest limit on what this mechanism provides. Printed by the gate on
/// every run and carried in every [`Resolution`], so no consumer can quote
/// the derived number without also being handed this sentence.
pub const LIMITATION: &str = concat!(
    "No gate makes a physical enclosure real. This mechanism checks only ",
    "that the enclosure CLAIM is explicit, internally consistent, anchored ",
    "to a resolvable commit, and unchanged since the verification that ",
    "backs it. It cannot observe a cover, a gasket, or an airflow path. ",
    "The sealing itself is a manufacturing and QA matter."
);

/// The schema version this module understands.
pub const SUPPORTED_SCHEMA_VERSION: u64 = 1;

/// The working-voltage bracket the mains<->SELV barrier is classified in.
/// Row iv of recovered Table 17 (`>250-400` V).
pub const BARRIER_VOLTAGE_RANGE: VoltageRange = VoltageRange::Gt250Le400;

/// Generic FR-4: material group IIIa/IIIb (Table 17 merges the two columns).
pub const BARRIER_MATERIAL_GROUP: MaterialGroup = MaterialGroup::IIIaOrIIIb;

// ---------------------------------------------------------------------------
// Declared facts
// ---------------------------------------------------------------------------

/// The physical facts a declaration asserts about the PCB's enclosure.
///
/// Every field is an affirmative claim -- the `elec/domain_manifest.yaml`
/// shape, where a thing is true only because someone wrote it down and a
/// gate can check it, never because a name or a default implied it.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct EnclosureFacts {
    /// The PCB sits in a compartment closed against ingress of conductive
    /// dust and condensation.
    pub sealed: bool,
    /// That compartment's closure is gasketed (a seal, not merely a lid).
    pub gasketed: bool,
    /// The compartment is kept OUT of the coil/heatsink forced-air path --
    /// the condition `docs/CHASSIS_AIRFLOW_DESIGN.md` describes this chassis
    /// as violating today (bottom intake -> 80 mm fan -> IGBT-heatsink duct
    /// -> rear exhaust, across the cavity the PCB occupies).
    pub outside_forced_air_path: bool,
}

impl EnclosureFacts {
    /// Whether the declared facts satisfy every precondition of the PD2
    /// exception. Naming this separately from [`pollution_degree_for`] is
    /// deliberate: the caller needs to know *whether resolvable verification
    /// evidence is load-bearing* before it decides to go and resolve it.
    pub fn qualifies_for_pd2_exception(&self) -> bool {
        self.sealed && self.gasketed && self.outside_forced_air_path
    }
}

/// The pollution degree implied by a set of declared enclosure facts.
///
/// Total and conservative: [`PollutionDegree::PD2`] only when every
/// precondition of the IEC 60335-2-6 cl. 29.2 Addition exception holds, and
/// [`PollutionDegree::PD3`] -- the larger creepage requirement -- otherwise.
/// PD1 is unreachable by design (see the module docstring).
pub fn pollution_degree_for(facts: &EnclosureFacts) -> PollutionDegree {
    if facts.qualifies_for_pd2_exception() {
        PollutionDegree::PD2
    } else {
        PollutionDegree::PD3
    }
}

/// The reinforced mains<->SELV creepage requirement at a given pollution
/// degree: recovered Table 17 row iv, group IIIa/IIIb, doubled per cl. 29.2.3.
///
/// Panics only if the `const` Table 17 in [`crate::safety_value`] is
/// internally inconsistent -- a programming error, not a data condition.
pub fn reinforced_barrier_creepage(pd: PollutionDegree) -> SafetyValue {
    let group = BARRIER_MATERIAL_GROUP;
    let range = BARRIER_VOLTAGE_RANGE;
    let basic = table_17_lookup(pd, group, range).unwrap_or_else(|| {
        panic!("internal error: recovered Table 17 has no cell for ({pd}, {group}, {range})")
    });
    creepage_reinforced(basic)
}

// ---------------------------------------------------------------------------
// Declaration document
// ---------------------------------------------------------------------------

/// The dated, commit-anchored verification behind an [`EnclosureFacts`].
#[derive(Debug, Clone, PartialEq, Eq, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Verification {
    /// ISO date the physical state was checked.
    pub verified_on: String,
    /// Who or what performed the check.
    pub verified_by: String,
    /// How it was checked. Free text for a human; never parsed.
    pub method: String,
    /// The commit whose tree the check was performed against. 40 lowercase
    /// hex characters, and it must **resolve** -- see the module docstring on
    /// why `"UNKNOWN"` is not accepted here the way it is for an advisory
    /// measurement anchor.
    pub measured_at_commit: String,
    /// Repo-relative paths to the artifacts recording the check.
    pub artifacts: Vec<String>,
    /// sha256 of the canonical form of the `enclosure:` block this
    /// verification covers. A mismatch means the physical claim was edited
    /// after it was verified -- i.e. the declaration is stale.
    pub declared_state_sha256: String,
}

/// A parsed `elec/enclosure_manifest.yaml`.
#[derive(Debug, Clone, PartialEq, Eq, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Declaration {
    pub schema_version: u64,
    pub enclosure: EnclosureFacts,
    pub verification: Verification,
}

/// Everything that can make a declaration unusable. Every variant is a hard
/// failure; there is deliberately no "warn and continue" outcome, because the
/// only outcome a silent fallback could produce is a safety number selected
/// by something other than the declaration.
#[derive(Debug, Clone, PartialEq, Eq, thiserror::Error)]
pub enum DeclarationError {
    #[error("enclosure declaration is empty")]
    Empty,
    #[error("enclosure declaration could not be parsed: {0}")]
    Unparseable(String),
    #[error(
        "enclosure declaration schema_version is {found}, this build understands {SUPPORTED_SCHEMA_VERSION}"
    )]
    UnsupportedSchemaVersion { found: u64 },
    #[error("verification.{field} is empty or a placeholder ({value:?})")]
    PlaceholderField { field: String, value: String },
    #[error(
        "verification.measured_at_commit must be 40 lowercase hex characters naming the commit the enclosure was verified at; got {value:?}"
    )]
    MalformedVerificationCommit { value: String },
    #[error(
        "verification.measured_at_commit {value} does not resolve to a commit in this repository: the declaration claims traceability it does not have. Pollution degree 2 is unselectable without resolvable enclosure evidence."
    )]
    UnresolvableVerificationCommit { value: String },
    #[error(
        "enclosure declaration is STALE: verification.declared_state_sha256 is {declared}, but the enclosure: block present in the file digests to {computed}. The physical claim was edited after the verification that backs it; re-verify and update the digest."
    )]
    StaleDeclaration { declared: String, computed: String },
}

/// Canonical digest of an [`EnclosureFacts`].
///
/// Hashes a canonical rendering of the *parsed* facts -- sorted, one
/// `key=value` per line -- not the file bytes. Comments, key order, and YAML
/// formatting are therefore free to change; only a change to a declared
/// physical fact moves the digest. That is the property that makes a
/// mismatch mean "the claim changed" rather than "someone reflowed a
/// comment".
pub fn canonical_facts_digest(facts: &EnclosureFacts) -> String {
    // Written out field by field, in a fixed order, rather than serialised:
    // a derive-driven serialisation would silently change the digest of every
    // committed declaration if a field were renamed or reordered, turning a
    // refactor into a repo-wide "stale declaration" failure with no physical
    // change behind it.
    let canonical = format!(
        "gasketed={}\noutside_forced_air_path={}\nsealed={}\n",
        facts.gasketed, facts.outside_forced_air_path, facts.sealed
    );
    let mut hasher = Sha256::new();
    hasher.update(canonical.as_bytes());
    format!("{:x}", hasher.finalize())
}

/// The outcome of resolving a declaration: the classification, the derived
/// requirement, and the honest limit on what any of it proves.
#[derive(Debug, Clone, PartialEq)]
pub struct Resolution {
    pub facts: EnclosureFacts,
    pub pollution_degree: PollutionDegree,
    /// The derived reinforced HV<->SELV creepage requirement, carrying its
    /// full provenance chain back to the recovered Table 17 cell.
    pub barrier_creepage: SafetyValue,
    pub verified_on: String,
    pub measured_at_commit: String,
    /// True when the declared facts made the verification commit's
    /// resolvability load-bearing (i.e. the PD2 exception was claimed).
    pub pd2_exception_claimed: bool,
}

impl Resolution {
    /// The derived requirement in millimetres.
    pub fn barrier_width_mm(&self) -> f64 {
        self.barrier_creepage.value_mm()
    }

    /// The honest limit. Constant, but exposed as a method so no consumer can
    /// obtain the number without the sentence being one call away.
    pub fn limitation(&self) -> &'static str {
        LIMITATION
    }
}

fn is_placeholder(value: &str) -> bool {
    let trimmed = value.trim();
    trimmed.is_empty()
        || matches!(
            trimmed.to_ascii_uppercase().as_str(),
            "TBD" | "TODO" | "UNKNOWN" | "N/A" | "NONE" | "XXX" | "FIXME"
        )
}

fn is_forty_hex(value: &str) -> bool {
    value.len() == 40 && value.bytes().all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
}

/// Parse, validate, and evaluate an enclosure declaration.
///
/// `evidence_resolved` is the caller's proof that
/// `verification.measured_at_commit` resolves to a real commit object. It is
/// an input rather than something this module discovers because resolving it
/// requires a git object store, which does not exist on the `wasm32` tier and
/// must not be assumed by a library import. Callers that cannot check pass
/// `false`; the result is that a PD2-claiming declaration fails closed, which
/// is the intended direction.
///
/// Ordering matters and is deliberate: staleness is checked **before** the
/// PD2/evidence rule, so "flipped to sealed without re-verifying" is reported
/// as the stale-declaration it is rather than as a missing-evidence problem.
pub fn resolve(yaml_text: &str, evidence_resolved: bool) -> Result<Resolution, DeclarationError> {
    if yaml_text.trim().is_empty() {
        return Err(DeclarationError::Empty);
    }

    let declaration: Declaration =
        serde_yaml::from_str(yaml_text).map_err(|e| DeclarationError::Unparseable(e.to_string()))?;

    if declaration.schema_version != SUPPORTED_SCHEMA_VERSION {
        return Err(DeclarationError::UnsupportedSchemaVersion {
            found: declaration.schema_version,
        });
    }

    let v = &declaration.verification;
    for (field, value) in [
        ("verified_on", &v.verified_on),
        ("verified_by", &v.verified_by),
        ("method", &v.method),
        ("declared_state_sha256", &v.declared_state_sha256),
    ] {
        if is_placeholder(value) {
            return Err(DeclarationError::PlaceholderField {
                field: field.to_string(),
                value: value.clone(),
            });
        }
    }
    if v.artifacts.is_empty() || v.artifacts.iter().any(|a| is_placeholder(a)) {
        return Err(DeclarationError::PlaceholderField {
            field: "artifacts".to_string(),
            value: format!("{:?}", v.artifacts),
        });
    }
    if !is_forty_hex(&v.measured_at_commit) {
        return Err(DeclarationError::MalformedVerificationCommit {
            value: v.measured_at_commit.clone(),
        });
    }

    let computed = canonical_facts_digest(&declaration.enclosure);
    if computed != v.declared_state_sha256.trim().to_ascii_lowercase() {
        return Err(DeclarationError::StaleDeclaration {
            declared: v.declared_state_sha256.clone(),
            computed,
        });
    }

    let pd2_exception_claimed = declaration.enclosure.qualifies_for_pd2_exception();
    if pd2_exception_claimed && !evidence_resolved {
        return Err(DeclarationError::UnresolvableVerificationCommit {
            value: v.measured_at_commit.clone(),
        });
    }

    let pollution_degree = pollution_degree_for(&declaration.enclosure);
    Ok(Resolution {
        facts: declaration.enclosure,
        pollution_degree,
        barrier_creepage: reinforced_barrier_creepage(pollution_degree),
        verified_on: v.verified_on.clone(),
        measured_at_commit: v.measured_at_commit.clone(),
        pd2_exception_claimed,
    })
}

// ---------------------------------------------------------------------------
// pyo3 surface
// ---------------------------------------------------------------------------
//
// Thin binding only: the rule, the schema, the digest, and the fail-closed
// ordering all live in the Rust above, so the Python consumer
// (`temper_placer.core.enclosure_declaration`) cannot hold a second copy of
// any of them. It supplies exactly one thing Rust deliberately does not do --
// `evidence_resolved`, which needs a git object store.

#[cfg(feature = "python")]
use pyo3::exceptions::PyValueError;
#[cfg(feature = "python")]
use pyo3::prelude::*;

/// Python-visible [`Resolution`]. Frozen; constructed only by
/// [`resolve_enclosure_declaration`].
#[cfg(feature = "python")]
#[pyclass(frozen, skip_from_py_object, name = "EnclosureResolution")]
#[derive(Clone, Debug)]
pub struct PyEnclosureResolution {
    inner: Resolution,
}

#[cfg(feature = "python")]
#[pymethods]
impl PyEnclosureResolution {
    /// `2` or `3`. Never `1` -- see the module docstring on PD1.
    fn pollution_degree(&self) -> u8 {
        match self.inner.pollution_degree {
            PollutionDegree::PD1 => 1,
            PollutionDegree::PD2 => 2,
            PollutionDegree::PD3 => 3,
        }
    }

    /// The derived reinforced HV<->SELV creepage requirement, in mm.
    fn barrier_width_mm(&self) -> f64 {
        self.inner.barrier_width_mm()
    }

    /// The full provenance chain of that number, back to the recovered
    /// Table 17 cell and the clause that doubles it.
    fn provenance_debug(&self) -> String {
        self.inner.barrier_creepage.provenance_debug()
    }

    fn sealed(&self) -> bool {
        self.inner.facts.sealed
    }

    fn gasketed(&self) -> bool {
        self.inner.facts.gasketed
    }

    fn outside_forced_air_path(&self) -> bool {
        self.inner.facts.outside_forced_air_path
    }

    fn verified_on(&self) -> String {
        self.inner.verified_on.clone()
    }

    fn measured_at_commit(&self) -> String {
        self.inner.measured_at_commit.clone()
    }

    /// True when the declared facts made the verification commit's
    /// resolvability load-bearing.
    fn pd2_exception_claimed(&self) -> bool {
        self.inner.pd2_exception_claimed
    }

    /// The honest limit on what any of this proves.
    fn limitation(&self) -> &'static str {
        LIMITATION
    }

    fn __repr__(&self) -> String {
        format!(
            "EnclosureResolution(pollution_degree={}, barrier_width_mm={}, verified_on={:?})",
            self.pollution_degree(),
            self.inner.barrier_width_mm(),
            self.inner.verified_on
        )
    }
}

/// Parse, validate and evaluate an enclosure declaration.
///
/// `evidence_resolved` must be the caller's *verified* answer to "does
/// `verification.measured_at_commit` resolve to a real commit object here?".
/// Passing `False` when unsure is correct and safe: it makes a PD2-claiming
/// declaration fail closed.
///
/// Raises `ValueError` -- never returns a fallback -- on an empty,
/// unparseable, wrong-schema, placeholder, malformed-commit, stale, or
/// (for a PD2 claim) unresolvable declaration.
#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(signature = (yaml_text, evidence_resolved))]
fn resolve_enclosure_declaration(
    yaml_text: &str,
    evidence_resolved: bool,
) -> PyResult<PyEnclosureResolution> {
    match resolve(yaml_text, evidence_resolved) {
        Ok(inner) => Ok(PyEnclosureResolution { inner }),
        Err(e) => Err(PyValueError::new_err(e.to_string())),
    }
}

/// The canonical digest of a set of declared enclosure facts -- the value
/// that belongs in `verification.declared_state_sha256`. Exposed so the gate
/// can report the digest a stale declaration should have carried, and so a
/// human re-verifying the enclosure can compute it without hand-hashing.
#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(signature = (sealed, gasketed, outside_forced_air_path))]
fn enclosure_facts_digest(
    sealed: bool,
    gasketed: bool,
    outside_forced_air_path: bool,
) -> String {
    canonical_facts_digest(&EnclosureFacts {
        sealed,
        gasketed,
        outside_forced_air_path,
    })
}

/// The pollution degree implied by a set of enclosure facts, with no
/// document, verification or evidence around it. Exposed for differential and
/// property testing of the rule itself; production callers must go through
/// [`resolve_enclosure_declaration`], which is the only path that also
/// enforces staleness and evidence resolvability.
#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(signature = (sealed, gasketed, outside_forced_air_path))]
fn enclosure_pollution_degree(sealed: bool, gasketed: bool, outside_forced_air_path: bool) -> u8 {
    match pollution_degree_for(&EnclosureFacts {
        sealed,
        gasketed,
        outside_forced_air_path,
    }) {
        PollutionDegree::PD1 => 1,
        PollutionDegree::PD2 => 2,
        PollutionDegree::PD3 => 3,
    }
}

/// The honest limit, as a module-level constant Python can read.
#[cfg(feature = "python")]
#[pyfunction]
fn enclosure_mechanism_limitation() -> &'static str {
    LIMITATION
}

/// Register the enclosure surface on the `temper_design_bundle_python` module.
#[cfg(feature = "python")]
pub fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<PyEnclosureResolution>()?;
    module.add_function(wrap_pyfunction!(resolve_enclosure_declaration, module)?)?;
    module.add_function(wrap_pyfunction!(enclosure_facts_digest, module)?)?;
    module.add_function(wrap_pyfunction!(enclosure_pollution_degree, module)?)?;
    module.add_function(wrap_pyfunction!(enclosure_mechanism_limitation, module)?)?;
    Ok(())
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

    const GOOD_COMMIT: &str = "a2f3aaa648d5a5204134f0e36cb34072149c1b46";

    fn manifest(sealed: bool, gasketed: bool, outside: bool, digest: &str, commit: &str) -> String {
        format!(
            "schema_version: 1\n\
             enclosure:\n  \
               sealed: {sealed}\n  \
               gasketed: {gasketed}\n  \
               outside_forced_air_path: {outside}\n\
             verification:\n  \
               verified_on: \"2026-08-15\"\n  \
               verified_by: \"agent\"\n  \
               method: \"inspection\"\n  \
               measured_at_commit: \"{commit}\"\n  \
               artifacts:\n    - \"docs/evidence/x.md\"\n  \
               declared_state_sha256: \"{digest}\"\n"
        )
    }

    fn as_built() -> EnclosureFacts {
        EnclosureFacts {
            sealed: false,
            gasketed: false,
            outside_forced_air_path: false,
        }
    }

    fn compartment() -> EnclosureFacts {
        EnclosureFacts {
            sealed: true,
            gasketed: true,
            outside_forced_air_path: true,
        }
    }

    /// Exhaustive over all 2^3 declarable fact combinations: PD2 is reachable
    /// from exactly one of them, PD3 from the other seven, and PD1 from none.
    #[cfg_attr(test, test)]
    pub fn pollution_degree_rule_is_exhaustively_conservative() {
        let mut pd2_count = 0;
        for bits in 0u8..8 {
            let facts = EnclosureFacts {
                sealed: bits & 1 != 0,
                gasketed: bits & 2 != 0,
                outside_forced_air_path: bits & 4 != 0,
            };
            let pd = pollution_degree_for(&facts);
            assert_ne!(pd, PollutionDegree::PD1, "PD1 must be unreachable: {facts:?}");
            if facts.sealed && facts.gasketed && facts.outside_forced_air_path {
                assert_eq!(pd, PollutionDegree::PD2, "{facts:?}");
                pd2_count += 1;
            } else {
                assert_eq!(pd, PollutionDegree::PD3, "{facts:?}");
            }
        }
        assert_eq!(pd2_count, 1);
    }

    /// The derivation reaches the enforced figure through the recovered
    /// table, not through a literal: 6.3 mm basic x2 = 12.6 mm at PD3.
    #[cfg_attr(test, test)]
    pub fn as_built_facts_derive_12_6_through_recovered_table_17() {
        let pd = pollution_degree_for(&as_built());
        assert_eq!(pd, PollutionDegree::PD3);
        let value = reinforced_barrier_creepage(pd);
        assert_eq!(value.value_mm(), 12.6);
        assert!(!value.is_fabricated());
        assert!(!value.is_unobtainable());
        let debug = value.provenance_debug();
        assert!(debug.contains("Table 17"), "{debug}");
        assert!(debug.contains("29.2.3"), "{debug}");
    }

    /// The counterfactual arm: a real compartment derives 8.0 mm through the
    /// same call, so the rule is not a constant function of its input.
    #[cfg_attr(test, test)]
    pub fn compartment_facts_derive_8_0_through_the_same_path() {
        let pd = pollution_degree_for(&compartment());
        assert_eq!(pd, PollutionDegree::PD2);
        assert_eq!(reinforced_barrier_creepage(pd).value_mm(), 8.0);
    }

    #[cfg_attr(test, test)]
    pub fn digest_tracks_facts_and_ignores_formatting() {
        let a = canonical_facts_digest(&as_built());
        let b = canonical_facts_digest(&as_built());
        assert_eq!(a, b, "digest must be deterministic");
        assert_ne!(a, canonical_facts_digest(&compartment()));
        assert_eq!(a.len(), 64);
    }

    #[cfg_attr(test, test)]
    pub fn resolve_accepts_the_as_built_declaration_without_git() {
        let digest = canonical_facts_digest(&as_built());
        // evidence_resolved = false: the as-built (PD3) declaration does not
        // make the commit's resolvability load-bearing.
        let r = resolve(&manifest(false, false, false, &digest, GOOD_COMMIT), false)
            .expect("as-built declaration must resolve");
        assert_eq!(r.pollution_degree, PollutionDegree::PD3);
        assert_eq!(r.barrier_width_mm(), 12.6);
        assert!(!r.pd2_exception_claimed);
        assert!(r.limitation().contains("No gate makes a physical enclosure real"));
    }

    #[cfg_attr(test, test)]
    pub fn resolve_rejects_pd2_claim_without_resolvable_evidence() {
        let digest = canonical_facts_digest(&compartment());
        let yaml = manifest(true, true, true, &digest, GOOD_COMMIT);
        assert!(matches!(
            resolve(&yaml, false),
            Err(DeclarationError::UnresolvableVerificationCommit { .. })
        ));
        // ... and accepts it once the evidence resolves.
        let r = resolve(&yaml, true).expect("resolvable evidence must admit PD2");
        assert_eq!(r.pollution_degree, PollutionDegree::PD2);
        assert_eq!(r.barrier_width_mm(), 8.0);
        assert!(r.pd2_exception_claimed);
    }

    #[cfg_attr(test, test)]
    pub fn resolve_rejects_facts_edited_after_verification() {
        // The digest of the as-built state, pasted beside a flipped claim --
        // the exact shape of "someone flipped sealed: true and shipped it".
        let stale = canonical_facts_digest(&as_built());
        assert!(matches!(
            resolve(&manifest(true, true, true, &stale, GOOD_COMMIT), true),
            Err(DeclarationError::StaleDeclaration { .. })
        ));
    }

    #[cfg_attr(test, test)]
    pub fn resolve_rejects_malformed_empty_and_unknown_inputs() {
        let digest = canonical_facts_digest(&as_built());
        assert!(matches!(resolve("", true), Err(DeclarationError::Empty)));
        assert!(matches!(
            resolve("not: a: declaration", true),
            Err(DeclarationError::Unparseable(_))
        ));
        assert!(matches!(
            resolve(&manifest(false, false, false, &digest, "UNKNOWN"), true),
            Err(DeclarationError::MalformedVerificationCommit { .. })
        ));
        // A well-formed but all-zero SHA is a *resolvability* question, not a
        // shape one -- exactly the ceiling corpus's dead "fully-evidenced"
        // control. It passes the shape check here and is caught by the
        // evidence check the moment PD2 is claimed (and by the gate always).
        assert!(resolve(&manifest(false, false, false, &digest, &"0".repeat(40)), false).is_ok());
        let zero_pd2_digest = canonical_facts_digest(&compartment());
        assert!(matches!(
            resolve(&manifest(true, true, true, &zero_pd2_digest, &"0".repeat(40)), false),
            Err(DeclarationError::UnresolvableVerificationCommit { .. })
        ));
        assert!(matches!(
            resolve(&manifest(false, false, false, &digest, "A2F3AAA648D5A5204134F0E36CB34072149C1B46"), true),
            Err(DeclarationError::MalformedVerificationCommit { .. })
        ));
        let bumped = manifest(false, false, false, &digest, GOOD_COMMIT)
            .replace("schema_version: 1", "schema_version: 2");
        assert!(matches!(
            resolve(&bumped, true),
            Err(DeclarationError::UnsupportedSchemaVersion { found: 2 })
        ));
    }

    #[cfg_attr(test, test)]
    pub fn resolve_rejects_unknown_and_placeholder_fields() {
        let digest = canonical_facts_digest(&as_built());
        let with_extra = manifest(false, false, false, &digest, GOOD_COMMIT)
            .replace("enclosure:\n", "enclosure:\n  pollution_degree: 2\n");
        assert!(
            matches!(resolve(&with_extra, true), Err(DeclarationError::Unparseable(_))),
            "declaring the answer inside the declaration must be rejected, not honoured"
        );
        let placeholder = manifest(false, false, false, &digest, GOOD_COMMIT)
            .replace("verified_by: \"agent\"", "verified_by: \"TBD\"");
        assert!(matches!(
            resolve(&placeholder, true),
            Err(DeclarationError::PlaceholderField { .. })
        ));
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("enclosure::tests::pollution_degree_rule_is_exhaustively_conservative", pollution_degree_rule_is_exhaustively_conservative),
        ("enclosure::tests::as_built_facts_derive_12_6_through_recovered_table_17", as_built_facts_derive_12_6_through_recovered_table_17),
        ("enclosure::tests::compartment_facts_derive_8_0_through_the_same_path", compartment_facts_derive_8_0_through_the_same_path),
        ("enclosure::tests::digest_tracks_facts_and_ignores_formatting", digest_tracks_facts_and_ignores_formatting),
        ("enclosure::tests::resolve_accepts_the_as_built_declaration_without_git", resolve_accepts_the_as_built_declaration_without_git),
        ("enclosure::tests::resolve_rejects_pd2_claim_without_resolvable_evidence", resolve_rejects_pd2_claim_without_resolvable_evidence),
        ("enclosure::tests::resolve_rejects_facts_edited_after_verification", resolve_rejects_facts_edited_after_verification),
        ("enclosure::tests::resolve_rejects_malformed_empty_and_unknown_inputs", resolve_rejects_malformed_empty_and_unknown_inputs),
        ("enclosure::tests::resolve_rejects_unknown_and_placeholder_fields", resolve_rejects_unknown_and_placeholder_fields),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}
