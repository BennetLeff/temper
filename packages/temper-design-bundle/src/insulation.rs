//! Per-pairing insulation coordination: declared working voltages ->
//! IEC 60335-1 Table 17/18 row -> required creepage, or an explicit
//! **not determinable**.
//!
//! ## What this module replaces, and why
//!
//! Until this module existed, the mains<->SELV creepage requirement on this
//! board was **one scalar** --
//! `MIN_BARRIER_WIDTH_MM = 12.6` in
//! `packages/temper-placer/src/temper_placer/core/isolation_constants.py` --
//! applied uniformly across a 27-net HV domain and a 35-net SELV domain.
//!
//! `docs/evidence/2026-08-19-table-17-row-determination-hv-selv.md`
//! ([`DOC_ROW_DETERMINATION`], commit `0cbc04248`) established from primary
//! text that a single scalar is the defect, not its value. The scalar is
//! **simultaneously too generous and too small**:
//!
//! | Pairing | Working V (r.m.s.) | Class | Table/row | Required |
//! |---|---|---|---|---|
//! | mains (`ac_l`, `PWR_RTN`, ...) <-> SELV | 120 V | reinforced | 17, ii | **4.8 mm** |
//! | DC bus (`+170V_BUS`, `DC_BUS_RTN`, ...) <-> SELV | 170 V d.c. | reinforced | 17, iii | **8.0 mm** |
//! | bus rail-to-rail | 340 V d.c. | **functional** | 18, iii | **5.0 mm** (undoubled) |
//! | switching (`SW_NODE`, `GATE_*`) <-> SELV | ~170 V **@ 47 kHz** | reinforced | **out of scope** | **not determinable** |
//! | tank <-> SELV | **>=570.5 V r.m.s. @ 47 kHz** | reinforced | 17, vi + out of scope | **>=20.0 mm**, not determinable |
//!
//! The 12.6 mm figure came from Table 17 row **iv** (>250-400 V), which suits
//! a 230 V design. This is a 120 V design whose doubler midpoint is Y-cap
//! coupled to PE, making `+170V_BUS` a **+/-170 V half-bus**, not a 340 V
//! rail. IEC 60664-1 cl. 3.2.1.1 dimensions creepage on *"the long-term
//! r.m.s. value"*, and 170 V d.c. with 120 V r.m.s. superimposed is 208.1 V
//! r.m.s. -- inside row iii. Only a *peak* basis reaches row iv, and
//! 60664-1 excludes the peak basis for creepage.
//!
//! ## The derivation chain
//!
//! ```text
//! elec/insulation_manifest.yaml   (declared groups, per-pairing working
//!                                  voltages, dated + digest-anchored)
//!   -> Declaration
//!   -> insulation_class_for()      (cl. 3.3.5 / cl. 29.2: cross-domain ->
//!                                   reinforced, same-domain -> functional)
//!   -> voltage_range_for(v_rms)    (IEC 60664-1 cl. 3.2.1.1: the r.m.s.
//!                                   value selects the Table row)
//!   -> table_17_lookup / table_18_lookup   (recovered tables)
//!   -> x2 for reinforced           (cl. 29.2.3)
//!   -> Requirement { Determined | IndeterminateWithFloor }
//! ```
//!
//! ## Fail-closed: the 47 kHz crossings have NO number
//!
//! IEC 60664-1 cl. 1.1.1 scopes the document to *"rated frequencies up to
//! 30 kHz"*, and cl. 2.3 states in full: *"Information on the dimensioning
//! for frequencies above 30 kHz is given in IEC 60664-4."* This board
//! switches at 47 kHz (`elec/src/main.ato:134`). Every pairing that touches
//! the switch node or the tank is therefore **above the frequency ceiling of
//! the document IEC 60335-1 cl. 29.2 points to for creepage measurement**,
//! and the dimensioning authority is IEC 60664-4 -- **paywalled and not
//! obtained**.
//!
//! Such a pairing is represented as
//! [`Requirement::IndeterminateWithFloor`]. Two properties are load-bearing:
//!
//! 1. **`requirement` is [`crate::safety_value::SafetyValue::is_unobtainable`]
//!    -- `NaN`, not a number.** Nothing in this module reconstructs, estimates
//!    or interpolates a 60664-4 value. A consumer that asks for "the
//!    requirement" of a 47 kHz pairing gets `NaN` and must branch.
//! 2. **`floor` is a proven LOWER BOUND, never a pass criterion.** It is the
//!    ordinary Table 17/18 lookup at the declared r.m.s. working voltage --
//!    i.e. what the requirement would be *if* the pairing were inside
//!    60664-1's scope. Since >30 kHz creepage requirements are not known to
//!    be more permissive than <=30 kHz ones (and the UL/CSA 6th Ed. has
//!    already written >30 kHz creepage into these same clauses -- see
//!    [`DOC_ROW_DETERMINATION`] §6.2), a geometry that fails the floor fails
//!    outright. A geometry that *clears* the floor is **not** thereby
//!    compliant: [`Requirement::is_determinable`] is `false` and
//!    [`Verdict::Indeterminate`] is the strongest verdict available.
//!
//! **`Verdict::Indeterminate` is not a pass.** Every consumer must treat it
//! as a non-pass -- see [`Verdict::is_pass`], which returns `false` for it,
//! and the gate `scripts/check_insulation_pairings.py`, which exits non-zero
//! on it. A gate that reports "cannot determine" is correct here; one that
//! silently applies 12.6 mm is not.
//!
//! ## What this module CANNOT do -- state this every time it is quoted
//!
//! See [`LIMITATION`]. Two independent limits:
//!
//! * **The 47 kHz requirement is unknown, not satisfied.** No amount of
//!   copper clears a requirement nobody has read. Closing this needs
//!   IEC 60664-4 (or the UL/CSA 6th Ed. text), which must be *bought*, not
//!   derived.
//! * **The tank<->SELV working voltage has never been measured in this
//!   repository.** 570.5 V r.m.s. is measured tank-to-*bus*
//!   (`docs/evidence/2026-08-12-hv-clearance-adequacy.md`, ngspice-42). The
//!   declaration carries that figure for the tank<->SELV pairing and says so;
//!   it is a measurement gap, not a standards gap, and it is cheap to close.
//!
//! ## Design notes
//!
//! * **Working voltages are declared per PAIRING, not per group.**
//!   cl. 3.1.3 defines working voltage as the voltage *"to which the part
//!   under consideration is subjected"* -- a property of a pair, not of a
//!   net. `+170V_BUS` is 170 V against SELV and 340 V against `DC_BUS_RTN`;
//!   no per-net number can express both, and `max(170, 170)` gets the
//!   rail-to-rail case wrong by a factor of two.
//! * **Insulation class is DERIVED, not declared.** Cross-domain ->
//!   reinforced (the separation this design's isolators are specified for),
//!   same-domain -> functional (cl. 3.3.5). Declaring it would let a
//!   declaration quietly downgrade a barrier crossing.
//! * **Completeness is enforced.** Every unordered pair of declared groups,
//!   *including self-pairs*, must have exactly one pairing entry, and every
//!   HV/SELV net of `elec/domain_manifest.yaml` must appear in exactly one
//!   group (checked by the gate, which is the only layer that can read the
//!   other manifest). A missing pairing is
//!   [`DeclarationError::MissingPairing`], not a default.
//! * **No pyo3 in the core.** The rule compiles under
//!   `--no-default-features` and onto the `wasm32` tier; the pyo3 surface is
//!   `#[cfg(feature = "python")]`-gated at the bottom.
//! * **Pollution degree is an INPUT.** It is not declared in this manifest
//!   and not defaulted here: it belongs to the enclosure, which is a
//!   different physical claim with its own declaration
//!   (`feat/enclosure-declaration-derives-pd`). Passing it in keeps this
//!   module composable with that one instead of holding a second copy of its
//!   answer.
//! * **Annex L's clearance-comparison step is deliberately NOT implemented,
//!   and here is why that is safe.** L-2 says a creepage distance is
//!   *"compared with the corresponding clearance of Table 16 and enlarged if
//!   necessary in order not to be less than the clearance."* Table 16 is
//!   keyed to *rated impulse voltage*, and the working-voltage -> rated-
//!   impulse mapping (Table 15) is not recovered in this repository for every
//!   pairing, so computing the step would mean inventing an input. It is
//!   non-binding regardless: at this board's 120 V nominal / 1500 V rated
//!   impulse, the recovered Table 16 basic clearance is 0.5 mm and even the
//!   reinforced step plus the soldered-construction adder is 2.0 mm
//!   (`scripts/generate_kicad_dru.py`'s `HV_INTERNAL_CLEARANCE_MM`), below
//!   every creepage figure this module derives (smallest: 1.8 mm functional
//!   SELV<->SELV; smallest cross-barrier: 4.8 mm). Stated rather than
//!   silently skipped.

use std::collections::BTreeMap;

use serde::Deserialize;
use sha2::{Digest, Sha256};

use crate::safety_value::{
    creepage_reinforced, table_17_lookup, table_18_lookup, unobtainable, MaterialGroup,
    PollutionDegree, SafetyValue, Standard, VoltageRange,
};

// ---------------------------------------------------------------------------
// Evidence documents (the determination this rule encodes)
// ---------------------------------------------------------------------------

/// The 2026-08-19 standards determination this module implements: per-pairing
/// Table 17/18 rows, the r.m.s. basis, and the >30 kHz gap.
pub const DOC_ROW_DETERMINATION: &str =
    "docs/evidence/2026-08-19-table-17-row-determination-hv-selv.md";

/// The tank's measured working voltage (570.5 V r.m.s. / 923.7 V peak,
/// ngspice-42, worst OCP-01-passing corner) and the flagged
/// "unconsidered high-frequency standard" hazard.
pub const DOC_TANK_WORKING_VOLTAGE: &str = "docs/evidence/2026-08-12-hv-clearance-adequacy.md";

/// The honest limit on what this mechanism provides. Printed by the gate on
/// every run and reachable from every [`Resolution`], so no consumer can quote
/// a derived number without the sentence being one call away.
pub const LIMITATION: &str = concat!(
    "Two limits, both structural. (1) FREQUENCY: this board switches at ",
    "47 kHz, above IEC 60664-1 cl. 1.1.1's 30 kHz scope ceiling; cl. 2.3 ",
    "routes dimensioning above it to IEC 60664-4, which is paywalled and ",
    "was NOT obtained. Every pairing touching the switch node or the tank ",
    "therefore has NO determinable requirement, only a proven lower bound ",
    "from the <=30 kHz tables. Clearing that bound is not compliance. ",
    "(2) MEASUREMENT: the tank<->SELV working voltage has never been ",
    "measured in this repository; 570.5 V r.m.s. is a tank-to-bus figure ",
    "carried forward. Neither gap is closable by any amount of copper or ",
    "any change to this code."
);

/// The schema version this module understands.
pub const SUPPORTED_SCHEMA_VERSION: u64 = 1;

/// IEC 60664-1 cl. 1.1.1: *"rated frequencies up to 30 kHz"*. Above this,
/// cl. 2.3 routes dimensioning to IEC 60664-4 (unobtainable).
pub const FREQUENCY_SCOPE_CEILING_HZ: f64 = 30_000.0;

/// Generic FR-4, CTI unstated: material group IIIa/IIIb. Table 17 and
/// Table 18 both merge IIIa and IIIb into one column, so the choice within
/// the merged group is immaterial.
///
/// Table 17 footnote 1) -- recovered in [`DOC_ROW_DETERMINATION`] -- reads
/// *"Material group IIIb is allowed if the working voltage does not exceed
/// 50 V."* Because the column is merged, that footnote does not move any
/// number here; it makes laminate CTI >= 175 (i.e. genuinely IIIa) a
/// **purchasing requirement** for every pairing above 50 V. Recorded here
/// because this is the only place the material group is chosen.
pub const MATERIAL_GROUP: MaterialGroup = MaterialGroup::IIIaOrIIIb;

/// The reason string carried by every indeterminate pairing's `requirement`.
const INDETERMINATE_REASON: &str = concat!(
    "above IEC 60664-1 cl. 1.1.1's 30 kHz scope ceiling; cl. 2.3 routes ",
    "dimensioning to IEC 60664-4, which is paywalled and was not obtained. ",
    "No value is reconstructed from it. The accompanying floor is the ",
    "<=30 kHz table figure and is a LOWER BOUND, not the requirement."
);

// ---------------------------------------------------------------------------
// Declared facts
// ---------------------------------------------------------------------------

/// Which side of the reinforced barrier a net group sits on.
///
/// Deliberately only two values. `elec/domain_manifest.yaml` declares exactly
/// two domains (`HV`, `SELV`) and this module's job is to grade pairs of them;
/// inventing a third would let a declaration place a group outside the
/// cross-domain/same-domain dichotomy that selects the insulation class.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Deserialize)]
pub enum Domain {
    /// Mains / high-voltage side.
    #[serde(rename = "HV")]
    Hv,
    /// Safety extra-low-voltage side (bonded to PE on this board:
    /// `elec/src/main.ato:753`, `gnd ~ pe`).
    #[serde(rename = "SELV")]
    Selv,
}

impl Domain {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Hv => "HV",
            Self::Selv => "SELV",
        }
    }
}

/// The insulation class a pairing is graded under.
///
/// Only the two classes this board's pairings actually take. Basic and
/// supplementary are not representable **on purpose**: every cross-domain
/// pairing here is specified as reinforced (the isolators are reinforced
/// parts), and admitting `Basic` would make a barrier crossing gradeable at
/// the undoubled Table 17 figure by a one-word change to a declaration.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum InsulationClass {
    /// cl. 3.3.5 -- *"insulation between conductive parts of different
    /// potential which is necessary only for the proper functioning of the
    /// appliance"*. Table 18, undoubled (cl. 29.2.4).
    Functional,
    /// Table 17, doubled (cl. 29.2.3: *"reinforced = at least double
    /// Table 17 basic"*).
    Reinforced,
}

impl InsulationClass {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Functional => "functional",
            Self::Reinforced => "reinforced",
        }
    }

    /// The table this class is graded against: Table 17 (doubled) for
    /// reinforced, Table 18 for functional.
    pub fn table_name(self) -> &'static str {
        match self {
            Self::Functional => "Table 18",
            Self::Reinforced => "Table 17",
        }
    }
}

/// The insulation class of a pairing, derived from the two groups' domains.
///
/// Cross-domain -> reinforced; same-domain -> functional (cl. 3.3.5). This is
/// a *function of the declared domains*, never a declared field: a
/// declaration that could name the class could downgrade a barrier crossing
/// to functional -- halving its requirement -- without changing any physical
/// claim.
pub fn insulation_class_for(a: Domain, b: Domain) -> InsulationClass {
    if a == b {
        InsulationClass::Functional
    } else {
        InsulationClass::Reinforced
    }
}

/// One declared group of nets that share a potential class and a frequency.
#[derive(Debug, Clone, PartialEq, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct GroupFacts {
    /// Which side of the barrier. Must agree with
    /// `elec/domain_manifest.yaml`; the gate checks it.
    pub domain: Domain,
    /// The exact, literal compiled net names in this group. Never a pattern
    /// or a prefix -- the same ground rule `elec/domain_manifest.yaml` states
    /// for itself, for the same reason (this design's net names have lied:
    /// `+340V_BUS` named the 170 V half-bus).
    pub nets: Vec<String>,
    /// The rated frequency of the potential these nets carry, in Hz. Above
    /// [`FREQUENCY_SCOPE_CEILING_HZ`] every pairing involving this group is
    /// not determinable.
    pub frequency_hz: f64,
    /// Where the frequency and the group membership come from. Free text for
    /// a human; never parsed.
    pub basis: String,
}

/// One declared pairing: two group names and the working voltage across them.
#[derive(Debug, Clone, PartialEq, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PairingFacts {
    pub a: String,
    pub b: String,
    /// The long-term r.m.s. value of the voltage existing across this pairing,
    /// in volts. IEC 60664-1 cl. 3.2.1.1: *"the basis for the determination
    /// of a creepage distance is the long-term r.m.s. value of the voltage
    /// existing across it"*. A d.c. rail's r.m.s. value is its d.c. value.
    pub working_voltage_vrms: f64,
    /// Where that number comes from -- a measurement, a clause, or a
    /// composition of both, cited. Free text for a human; never parsed.
    pub basis: String,
}

/// The dated, digest-anchored verification behind a set of declared facts.
///
/// Same shape as `elec/enclosure_manifest.yaml`'s, deliberately: this is the
/// repo's established pattern for "a claim that a gate can check is current",
/// and a second shape would be a second thing to learn.
#[derive(Debug, Clone, PartialEq, Eq, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Verification {
    /// ISO date the working voltages and group memberships were checked.
    pub verified_on: String,
    /// Who or what performed the check.
    pub verified_by: String,
    /// How it was checked. Free text for a human; never parsed.
    pub method: String,
    /// The commit whose tree the check was performed against. 40 lowercase
    /// hex characters.
    pub measured_at_commit: String,
    /// Repo-relative paths to the artifacts recording the check.
    pub artifacts: Vec<String>,
    /// sha256 of the canonical form of the `groups:` + `pairings:` blocks this
    /// verification covers. A mismatch means a working voltage or a group
    /// membership was edited after it was verified.
    pub declared_state_sha256: String,
}

/// A parsed `elec/insulation_manifest.yaml`.
#[derive(Debug, Clone, PartialEq, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Declaration {
    pub schema_version: u64,
    pub groups: BTreeMap<String, GroupFacts>,
    pub pairings: Vec<PairingFacts>,
    pub verification: Verification,
}

// ---------------------------------------------------------------------------
// Errors
// ---------------------------------------------------------------------------

/// Everything that can make a declaration unusable. Every variant is a hard
/// failure; there is deliberately no "warn and continue" outcome, because the
/// only outcome a silent fallback could produce is a safety number selected by
/// something other than the declaration.
// Not `Eq`: three variants carry the offending `f64` so the message can quote
// it, and `f64` is not `Eq`. `PartialEq` is what the tests need.
#[derive(Debug, Clone, PartialEq, thiserror::Error)]
pub enum DeclarationError {
    #[error("insulation declaration is empty")]
    Empty,
    #[error("insulation declaration could not be parsed: {0}")]
    Unparseable(String),
    #[error(
        "insulation declaration schema_version is {found}, this build understands {SUPPORTED_SCHEMA_VERSION}"
    )]
    UnsupportedSchemaVersion { found: u64 },
    #[error("verification.{field} is empty or a placeholder ({value:?})")]
    PlaceholderField { field: String, value: String },
    #[error(
        "verification.measured_at_commit must be 40 lowercase hex characters naming the commit the working voltages were verified at; got {value:?}"
    )]
    MalformedVerificationCommit { value: String },
    #[error(
        "insulation declaration is STALE: verification.declared_state_sha256 is {declared}, but the groups+pairings present in the file digest to {computed}. A working voltage or a group membership was edited after the verification that backs it; re-verify and update the digest."
    )]
    StaleDeclaration { declared: String, computed: String },
    #[error("insulation declaration declares no net groups; there is nothing to grade")]
    NoGroups,
    #[error("group {group:?} declares no nets; an empty group would make its pairings vacuous")]
    EmptyGroup { group: String },
    #[error(
        "group {group:?} declares frequency_hz = {value}; a frequency must be finite and >= 0"
    )]
    BadFrequency { group: String, value: f64 },
    #[error("group {group:?} has an empty basis; a declared fact with no provenance is not a fact")]
    MissingGroupBasis { group: String },
    #[error("pairing ({a:?}, {b:?}) names group {missing:?}, which is not declared")]
    UnknownGroup { a: String, b: String, missing: String },
    #[error(
        "pairing ({a:?}, {b:?}) declares working_voltage_vrms = {value}; a working voltage must be finite and > 0"
    )]
    BadWorkingVoltage { a: String, b: String, value: f64 },
    #[error(
        "pairing ({a:?}, {b:?}) has an empty basis; a working voltage with no provenance is a fabricated safety value"
    )]
    MissingPairingBasis { a: String, b: String },
    #[error("pairing ({a:?}, {b:?}) is declared more than once")]
    DuplicatePairing { a: String, b: String },
    #[error(
        "no pairing is declared for groups ({a:?}, {b:?}). Every unordered pair of declared groups, INCLUDING self-pairs, needs an explicit working voltage: an undeclared pairing has no requirement, and defaulting one would be inventing a safety value."
    )]
    MissingPairing { a: String, b: String },
    #[error("net {net:?} is declared in more than one group ({first:?} and {second:?})")]
    DuplicateNet {
        net: String,
        first: String,
        second: String,
    },
    #[error(
        "working voltage {value} V for pairing ({a:?}, {b:?}) is above the highest transcribed row of {table}; the recovered tables stop at 12 500 V and no value may be extrapolated"
    )]
    VoltageAboveTable {
        a: String,
        b: String,
        value: f64,
        table: &'static str,
    },
    #[error("pollution degree {found} is not 1, 2 or 3")]
    BadPollutionDegree { found: u8 },
}

// ---------------------------------------------------------------------------
// The rule
// ---------------------------------------------------------------------------

/// The Table 17/18 row a long-term r.m.s. working voltage selects.
///
/// IEC 60664-1 cl. 3.2.1.1 -- *"the basis for the determination of a creepage
/// distance is the long-term r.m.s. value of the voltage existing across
/// it"*. Boundaries are inclusive at the top (`<=50`, `>50-125`, ...) exactly
/// as the recovered tables print them, so 125.0 V is row ii and 125.01 V is
/// row iii.
///
/// Returns `None` above the highest transcribed row rather than saturating:
/// saturating would silently grade a 20 kV pairing at the 12.5 kV figure.
pub fn voltage_range_for(v_rms: f64) -> Option<VoltageRange> {
    const LADDER: [(f64, VoltageRange); 18] = [
        (50.0, VoltageRange::UpTo50),
        (125.0, VoltageRange::Gt50Le125),
        (250.0, VoltageRange::Gt125Le250),
        (400.0, VoltageRange::Gt250Le400),
        (500.0, VoltageRange::Gt400Le500),
        (800.0, VoltageRange::Gt500Le800),
        (1_000.0, VoltageRange::Gt800Le1000),
        (1_250.0, VoltageRange::Gt1000Le1250),
        (1_600.0, VoltageRange::Gt1250Le1600),
        (2_000.0, VoltageRange::Gt1600Le2000),
        (2_500.0, VoltageRange::Gt2000Le2500),
        (3_200.0, VoltageRange::Gt2500Le3200),
        (4_000.0, VoltageRange::Gt3200Le4000),
        (5_000.0, VoltageRange::Gt4000Le5000),
        (6_300.0, VoltageRange::Gt5000Le6300),
        (8_000.0, VoltageRange::Gt6300Le8000),
        (10_000.0, VoltageRange::Gt8000Le10000),
        (12_500.0, VoltageRange::Gt10000Le12500),
    ];
    LADDER
        .iter()
        .find(|(ceiling, _)| v_rms <= *ceiling)
        .map(|(_, range)| *range)
}

/// Whether a pairing's rated frequency is inside IEC 60664-1's declared
/// scope. `false` means the requirement is **not determinable**.
pub fn frequency_in_scope(frequency_hz: f64) -> bool {
    frequency_hz <= FREQUENCY_SCOPE_CEILING_HZ
}

/// The required creepage for one pairing.
///
/// Two shapes, and the distinction is the whole point of this type: a
/// consumer cannot accidentally read a number off an indeterminate pairing,
/// because the number it would read (`floor`) is behind a differently-named
/// accessor than the one it wants (`requirement`), and `requirement` is
/// `NaN`.
#[derive(Debug, Clone, PartialEq)]
pub enum Requirement {
    /// Inside IEC 60664-1's scope: the table figure IS the requirement.
    Determined(SafetyValue),
    /// Above the 30 kHz ceiling. The true requirement is unobtainable
    /// (IEC 60664-4); `floor` is the `<=30 kHz` table figure, a proven lower
    /// bound and **not** a pass criterion.
    IndeterminateWithFloor {
        /// Always [`SafetyValue::is_unobtainable`] -- `value_mm()` is `NaN`.
        requirement: SafetyValue,
        /// The `<=30 kHz` table figure. A necessary, NOT sufficient, bound.
        floor: SafetyValue,
    },
}

impl Requirement {
    /// `true` only when a real requirement exists. Consumers **must** branch
    /// on this before treating any number here as a compliance threshold.
    pub fn is_determinable(&self) -> bool {
        matches!(self, Self::Determined(_))
    }

    /// The requirement in millimetres, or `NaN` when indeterminate.
    ///
    /// Named for what it is. A consumer that wants "a number to compare
    /// against" and reaches for this gets `NaN` on the 47 kHz pairings, and
    /// every comparison against `NaN` is `false` -- which is the fail-closed
    /// direction for `measured >= required`.
    pub fn requirement_mm(&self) -> f64 {
        match self {
            Self::Determined(v) => v.value_mm(),
            Self::IndeterminateWithFloor { requirement, .. } => requirement.value_mm(),
        }
    }

    /// The largest distance this pairing is *known* to need: the requirement
    /// when determined, the proven lower bound when not.
    ///
    /// This is the figure a geometric constraint should be built from -- it is
    /// always real and always required -- but clearing it is only compliance
    /// when [`Requirement::is_determinable`] is `true`.
    pub fn enforceable_floor_mm(&self) -> f64 {
        match self {
            Self::Determined(v) => v.value_mm(),
            Self::IndeterminateWithFloor { floor, .. } => floor.value_mm(),
        }
    }

    /// The `SafetyValue` carrying the provenance of [`Self::enforceable_floor_mm`].
    pub fn floor_value(&self) -> &SafetyValue {
        match self {
            Self::Determined(v) => v,
            Self::IndeterminateWithFloor { floor, .. } => floor,
        }
    }

    /// One-line provenance of the figure, including the indeterminacy when
    /// it applies.
    pub fn provenance_debug(&self) -> String {
        match self {
            Self::Determined(v) => v.provenance_debug(),
            Self::IndeterminateWithFloor { requirement, floor } => format!(
                "NOT DETERMINABLE ({}) | proven lower bound {} mm from {}",
                requirement.provenance_debug(),
                floor.value_mm(),
                floor.provenance_debug()
            ),
        }
    }

    /// Grade a measured distance against this requirement.
    ///
    /// Deliberately three-valued. There is no input for which an
    /// indeterminate pairing returns [`Verdict::Pass`].
    pub fn grade(&self, measured_mm: f64) -> Verdict {
        let floor = self.enforceable_floor_mm();
        if !(measured_mm >= floor) {
            // `!(a >= b)` rather than `a < b` so a NaN measurement fails.
            return Verdict::Fail;
        }
        if self.is_determinable() {
            Verdict::Pass
        } else {
            Verdict::Indeterminate
        }
    }
}

/// The outcome of grading a measured distance against a [`Requirement`].
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum Verdict {
    /// Meets a determinable requirement.
    Pass,
    /// Below the requirement, or below the proven lower bound of an
    /// indeterminate one.
    Fail,
    /// Clears the proven lower bound, but the pairing's true requirement is
    /// not determinable from any standard this project can obtain.
    /// **Not a pass.**
    Indeterminate,
}

impl Verdict {
    /// `true` only for [`Verdict::Pass`]. [`Verdict::Indeterminate`] is not a
    /// pass -- this method exists so no consumer has to remember that.
    pub fn is_pass(self) -> bool {
        matches!(self, Self::Pass)
    }

    pub fn as_str(self) -> &'static str {
        match self {
            Self::Pass => "PASS",
            Self::Fail => "FAIL",
            Self::Indeterminate => "INDETERMINATE",
        }
    }
}

/// Derive the required creepage for one pairing from its class, working
/// voltage, frequency and pollution degree.
///
/// The whole rule, in one total function. `table` is chosen by the insulation
/// class (17 doubled / 18 undoubled), the row by the r.m.s. working voltage,
/// the column by (pollution degree, material group) -- and the frequency
/// decides whether the resulting figure is *the requirement* or merely *a
/// proven lower bound*.
pub fn required_creepage(
    class: InsulationClass,
    working_voltage_vrms: f64,
    frequency_hz: f64,
    pd: PollutionDegree,
) -> Option<Requirement> {
    let range = voltage_range_for(working_voltage_vrms)?;
    let basic = match class {
        InsulationClass::Reinforced => {
            let cell = table_17_lookup(pd, MATERIAL_GROUP, range)?;
            // cl. 29.2.3: reinforced is at least double the Table 17 figure.
            creepage_reinforced(cell)
        }
        // cl. 29.2.4: functional insulation is graded against Table 18
        // directly -- NOT doubled. Doubling here would charge a same-domain
        // pair a cross-barrier figure, the false-positive shape
        // scripts/generate_kicad_dru.py's RULE 4 comment records.
        InsulationClass::Functional => table_18_lookup(pd, MATERIAL_GROUP, range)?.clone(),
    };

    if frequency_in_scope(frequency_hz) {
        return Some(Requirement::Determined(basic));
    }
    Some(Requirement::IndeterminateWithFloor {
        requirement: unobtainable(Standard::IEC60664_4, INDETERMINATE_REASON),
        floor: basic,
    })
}

// ---------------------------------------------------------------------------
// Resolution
// ---------------------------------------------------------------------------

/// One pairing, fully resolved.
#[derive(Debug, Clone, PartialEq)]
pub struct PairingResolution {
    /// Group names, lexicographically ordered so a pairing has one identity.
    pub group_a: String,
    pub group_b: String,
    pub domain_a: Domain,
    pub domain_b: Domain,
    pub insulation: InsulationClass,
    pub working_voltage_vrms: f64,
    /// `max` of the two groups' declared frequencies -- the higher one is
    /// what carries the pairing out of IEC 60664-1's scope.
    pub frequency_hz: f64,
    pub voltage_range: VoltageRange,
    pub requirement: Requirement,
    /// The declared provenance of `working_voltage_vrms`.
    pub basis: String,
}

impl PairingResolution {
    /// True when this pairing crosses the reinforced barrier.
    pub fn crosses_barrier(&self) -> bool {
        self.domain_a != self.domain_b
    }

    /// A stable, human-readable pairing key, e.g. `"DC_BUS<->SELV"`.
    pub fn key(&self) -> String {
        format!("{}<->{}", self.group_a, self.group_b)
    }
}

/// The whole declaration, resolved.
#[derive(Debug, Clone, PartialEq)]
pub struct Resolution {
    pub pollution_degree: PollutionDegree,
    pub material_group: MaterialGroup,
    pub groups: BTreeMap<String, GroupFacts>,
    /// Every pairing, in a stable (group_a, group_b) order.
    pub pairings: Vec<PairingResolution>,
    pub verified_on: String,
    pub measured_at_commit: String,
}

impl Resolution {
    /// The group a net belongs to, or `None` if the net is not declared.
    ///
    /// `None` is not "no requirement": every caller that can see an undeclared
    /// net must treat it as an error. The gate
    /// `scripts/check_insulation_pairings.py` proves the declared net set
    /// covers `elec/domain_manifest.yaml` exactly, so a `None` here on a real
    /// board net means the two manifests have drifted.
    pub fn group_of(&self, net: &str) -> Option<&str> {
        self.groups
            .iter()
            .find(|(_, facts)| facts.nets.iter().any(|n| n == net))
            .map(|(name, _)| name.as_str())
    }

    /// The resolved pairing for two group names, in either order.
    pub fn pairing(&self, a: &str, b: &str) -> Option<&PairingResolution> {
        let (lo, hi) = ordered(a, b);
        self.pairings
            .iter()
            .find(|p| p.group_a == lo && p.group_b == hi)
    }

    /// The resolved pairing for two **net** names, in either order.
    pub fn pairing_for_nets(&self, net_a: &str, net_b: &str) -> Option<&PairingResolution> {
        let ga = self.group_of(net_a)?;
        let gb = self.group_of(net_b)?;
        self.pairing(ga, gb)
    }

    /// The worst (largest) enforceable floor over every pairing that crosses
    /// the reinforced barrier.
    ///
    /// This is the figure a single, geometric, whole-board barrier must be
    /// sized by, and it is why `MIN_BARRIER_WIDTH_MM` is not the DC-bus
    /// figure: one physical barrier separates the *whole* HV domain from the
    /// *whole* SELV domain, so it is governed by its worst crossing --
    /// [`DOC_ROW_DETERMINATION`] §6.1, *"They are the same physical barrier
    /// as rows 3 and 4 and are governed by whichever pairing is worst."*
    pub fn barrier_floor_mm(&self) -> f64 {
        self.pairings
            .iter()
            .filter(|p| p.crosses_barrier())
            .map(|p| p.requirement.enforceable_floor_mm())
            .fold(f64::NEG_INFINITY, f64::max)
    }

    /// The pairing that sets [`Self::barrier_floor_mm`].
    pub fn barrier_governing_pairing(&self) -> Option<&PairingResolution> {
        self.pairings
            .iter()
            .filter(|p| p.crosses_barrier())
            .max_by(|x, y| {
                x.requirement
                    .enforceable_floor_mm()
                    .total_cmp(&y.requirement.enforceable_floor_mm())
            })
    }

    /// `false` when ANY barrier-crossing pairing is indeterminate -- i.e. the
    /// barrier's true width requirement is unknown even though a lower bound
    /// for it is proven. Compliance of the barrier cannot be asserted while
    /// this is `false`, no matter how wide the barrier is.
    pub fn barrier_is_determinable(&self) -> bool {
        self.pairings
            .iter()
            .filter(|p| p.crosses_barrier())
            .all(|p| p.requirement.is_determinable())
    }

    /// Every pairing whose requirement is not determinable, in stable order.
    pub fn indeterminate_pairings(&self) -> Vec<&PairingResolution> {
        self.pairings
            .iter()
            .filter(|p| !p.requirement.is_determinable())
            .collect()
    }

    /// Every declared net, with its group.
    pub fn declared_nets(&self) -> BTreeMap<&str, &str> {
        let mut out = BTreeMap::new();
        for (name, facts) in &self.groups {
            for net in &facts.nets {
                out.insert(net.as_str(), name.as_str());
            }
        }
        out
    }

    /// The honest limit. Constant, but exposed as a method so no consumer can
    /// obtain a number without the sentence being one call away.
    pub fn limitation(&self) -> &'static str {
        LIMITATION
    }
}

fn ordered<'a>(a: &'a str, b: &'a str) -> (&'a str, &'a str) {
    if a <= b { (a, b) } else { (b, a) }
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

/// Canonical digest of the declared facts.
///
/// Hashes a canonical rendering of the *parsed* groups and pairings -- sorted,
/// one field per line -- not the file bytes. Comments, key order and YAML
/// formatting are free to change; only a change to a declared fact (a net's
/// group, a group's domain or frequency, a pairing's working voltage) moves
/// the digest. `basis` strings are **included**: a working voltage whose
/// justification changed is a different claim even at the same number.
pub fn canonical_facts_digest(
    groups: &BTreeMap<String, GroupFacts>,
    pairings: &[PairingFacts],
) -> String {
    // Written out field by field in a fixed order rather than serialised: a
    // derive-driven serialisation would change the digest of every committed
    // declaration if a field were renamed, turning a refactor into a
    // repo-wide "stale declaration" failure with no physical change behind it.
    let mut canonical = String::new();
    for (name, facts) in groups {
        let mut nets = facts.nets.clone();
        nets.sort();
        canonical.push_str(&format!(
            "group {name}: domain={} frequency_hz={} basis={} nets={}\n",
            facts.domain.as_str(),
            facts.frequency_hz,
            facts.basis.trim(),
            nets.join(","),
        ));
    }
    let mut rendered: Vec<String> = pairings
        .iter()
        .map(|p| {
            let (lo, hi) = ordered(&p.a, &p.b);
            format!(
                "pairing {lo}<->{hi}: v_rms={} basis={}\n",
                p.working_voltage_vrms,
                p.basis.trim()
            )
        })
        .collect();
    rendered.sort();
    for line in rendered {
        canonical.push_str(&line);
    }
    let mut hasher = Sha256::new();
    hasher.update(canonical.as_bytes());
    format!("{:x}", hasher.finalize())
}

/// Parse, validate and evaluate an insulation declaration.
///
/// `pollution_degree` is an input, not a declared field: it is a property of
/// the *enclosure*, which has its own declaration and its own rule
/// (`feat/enclosure-declaration-derives-pd`'s
/// `packages/temper-design-bundle/src/enclosure.rs`). Taking it here keeps
/// the two composable and stops this module holding a second copy of that
/// answer.
///
/// Ordering is deliberate: shape -> placeholders -> staleness -> completeness
/// -> derivation. Staleness is checked before completeness so "edited a
/// working voltage without re-verifying" is reported as the stale declaration
/// it is, rather than as whatever downstream inconsistency it happens to
/// create.
pub fn resolve(yaml_text: &str, pollution_degree: u8) -> Result<Resolution, DeclarationError> {
    let pd = PollutionDegree::from_u8(pollution_degree).ok_or(
        DeclarationError::BadPollutionDegree {
            found: pollution_degree,
        },
    )?;

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

    let computed = canonical_facts_digest(&declaration.groups, &declaration.pairings);
    if computed != v.declared_state_sha256.trim().to_ascii_lowercase() {
        return Err(DeclarationError::StaleDeclaration {
            declared: v.declared_state_sha256.clone(),
            computed,
        });
    }

    if declaration.groups.is_empty() {
        return Err(DeclarationError::NoGroups);
    }

    // Groups: non-empty, sane frequency, provenance, and no net in two groups.
    let mut net_owner: BTreeMap<&str, &str> = BTreeMap::new();
    for (name, facts) in &declaration.groups {
        if facts.nets.is_empty() {
            return Err(DeclarationError::EmptyGroup {
                group: name.clone(),
            });
        }
        if !facts.frequency_hz.is_finite() || facts.frequency_hz < 0.0 {
            return Err(DeclarationError::BadFrequency {
                group: name.clone(),
                value: facts.frequency_hz,
            });
        }
        if is_placeholder(&facts.basis) {
            return Err(DeclarationError::MissingGroupBasis {
                group: name.clone(),
            });
        }
        for net in &facts.nets {
            if let Some(first) = net_owner.insert(net.as_str(), name.as_str()) {
                return Err(DeclarationError::DuplicateNet {
                    net: net.clone(),
                    first: first.to_string(),
                    second: name.clone(),
                });
            }
        }
    }

    // Pairings: known groups, sane voltage, provenance, no duplicates.
    let mut seen: BTreeMap<(String, String), ()> = BTreeMap::new();
    for p in &declaration.pairings {
        for candidate in [&p.a, &p.b] {
            if !declaration.groups.contains_key(candidate) {
                return Err(DeclarationError::UnknownGroup {
                    a: p.a.clone(),
                    b: p.b.clone(),
                    missing: candidate.clone(),
                });
            }
        }
        if !p.working_voltage_vrms.is_finite() || p.working_voltage_vrms <= 0.0 {
            return Err(DeclarationError::BadWorkingVoltage {
                a: p.a.clone(),
                b: p.b.clone(),
                value: p.working_voltage_vrms,
            });
        }
        if is_placeholder(&p.basis) {
            return Err(DeclarationError::MissingPairingBasis {
                a: p.a.clone(),
                b: p.b.clone(),
            });
        }
        let (lo, hi) = ordered(&p.a, &p.b);
        if seen
            .insert((lo.to_string(), hi.to_string()), ())
            .is_some()
        {
            return Err(DeclarationError::DuplicatePairing {
                a: lo.to_string(),
                b: hi.to_string(),
            });
        }
    }

    // Completeness: every unordered pair of groups, including self-pairs.
    let names: Vec<&String> = declaration.groups.keys().collect();
    for (i, a) in names.iter().enumerate() {
        for b in names.iter().skip(i) {
            let (lo, hi) = ordered(a.as_str(), b.as_str());
            if !seen.contains_key(&(lo.to_string(), hi.to_string())) {
                return Err(DeclarationError::MissingPairing {
                    a: lo.to_string(),
                    b: hi.to_string(),
                });
            }
        }
    }

    // Derivation.
    let mut resolved: Vec<PairingResolution> = Vec::with_capacity(declaration.pairings.len());
    for p in &declaration.pairings {
        let (lo, hi) = ordered(&p.a, &p.b);
        let fa = &declaration.groups[lo];
        let fb = &declaration.groups[hi];
        let insulation = insulation_class_for(fa.domain, fb.domain);
        let frequency_hz = fa.frequency_hz.max(fb.frequency_hz);
        let range = voltage_range_for(p.working_voltage_vrms).ok_or(
            DeclarationError::VoltageAboveTable {
                a: lo.to_string(),
                b: hi.to_string(),
                value: p.working_voltage_vrms,
                table: insulation.table_name(),
            },
        )?;
        let requirement = required_creepage(insulation, p.working_voltage_vrms, frequency_hz, pd)
            .ok_or(DeclarationError::VoltageAboveTable {
                a: lo.to_string(),
                b: hi.to_string(),
                value: p.working_voltage_vrms,
                table: insulation.table_name(),
            })?;
        resolved.push(PairingResolution {
            group_a: lo.to_string(),
            group_b: hi.to_string(),
            domain_a: fa.domain,
            domain_b: fb.domain,
            insulation,
            working_voltage_vrms: p.working_voltage_vrms,
            frequency_hz,
            voltage_range: range,
            requirement,
            basis: p.basis.clone(),
        });
    }
    resolved.sort_by(|x, y| {
        (x.group_a.as_str(), x.group_b.as_str()).cmp(&(y.group_a.as_str(), y.group_b.as_str()))
    });

    Ok(Resolution {
        pollution_degree: pd,
        material_group: MATERIAL_GROUP,
        groups: declaration.groups,
        pairings: resolved,
        verified_on: v.verified_on.clone(),
        measured_at_commit: v.measured_at_commit.clone(),
    })
}

// ---------------------------------------------------------------------------
// pyo3 surface
// ---------------------------------------------------------------------------
//
// Thin binding only: the schema, the digest, the completeness rule, the
// table lookups and the frequency ceiling all live in the Rust above, so the
// Python consumer (`temper_placer.core.insulation_coordination`) cannot hold a
// second copy of any of them.

#[cfg(feature = "python")]
use pyo3::exceptions::PyValueError;
#[cfg(feature = "python")]
use pyo3::prelude::*;

/// Python-visible [`PairingResolution`].
#[cfg(feature = "python")]
#[pyclass(frozen, skip_from_py_object, name = "InsulationPairing")]
#[derive(Clone, Debug)]
pub struct PyInsulationPairing {
    inner: PairingResolution,
}

#[cfg(feature = "python")]
#[pymethods]
impl PyInsulationPairing {
    fn group_a(&self) -> &str {
        &self.inner.group_a
    }

    fn group_b(&self) -> &str {
        &self.inner.group_b
    }

    fn key(&self) -> String {
        self.inner.key()
    }

    fn domain_a(&self) -> &'static str {
        self.inner.domain_a.as_str()
    }

    fn domain_b(&self) -> &'static str {
        self.inner.domain_b.as_str()
    }

    /// `"reinforced"` or `"functional"` -- derived from the two domains,
    /// never declared.
    fn insulation(&self) -> &'static str {
        self.inner.insulation.as_str()
    }

    /// `"Table 17"` (doubled) or `"Table 18"` (undoubled).
    fn table(&self) -> &'static str {
        self.inner.insulation.table_name()
    }

    /// The recovered table row label, e.g. `">125-250"`.
    fn voltage_range(&self) -> &'static str {
        self.inner.voltage_range.as_str()
    }

    fn working_voltage_vrms(&self) -> f64 {
        self.inner.working_voltage_vrms
    }

    fn frequency_hz(&self) -> f64 {
        self.inner.frequency_hz
    }

    fn crosses_barrier(&self) -> bool {
        self.inner.crosses_barrier()
    }

    /// `True` only when a real requirement exists. **Branch on this before
    /// using any number from this object as a compliance threshold.**
    fn is_determinable(&self) -> bool {
        self.inner.requirement.is_determinable()
    }

    /// The requirement in mm, or `nan` when not determinable.
    fn requirement_mm(&self) -> f64 {
        self.inner.requirement.requirement_mm()
    }

    /// The largest distance this pairing is KNOWN to need: the requirement
    /// when determinable, the proven lower bound when not. Clearing it is
    /// compliance only when `is_determinable()`.
    fn enforceable_floor_mm(&self) -> f64 {
        self.inner.requirement.enforceable_floor_mm()
    }

    fn provenance_debug(&self) -> String {
        self.inner.requirement.provenance_debug()
    }

    /// The declared provenance of the working voltage.
    fn basis(&self) -> &str {
        &self.inner.basis
    }

    /// `"PASS"`, `"FAIL"` or `"INDETERMINATE"`. Never `"PASS"` for a pairing
    /// whose `is_determinable()` is `False`.
    fn grade(&self, measured_mm: f64) -> &'static str {
        self.inner.requirement.grade(measured_mm).as_str()
    }

    fn __repr__(&self) -> String {
        format!(
            "InsulationPairing({}, {}, {} V, {} Hz, {}, floor={} mm, determinable={})",
            self.inner.key(),
            self.inner.insulation.as_str(),
            self.inner.working_voltage_vrms,
            self.inner.frequency_hz,
            self.inner.voltage_range.as_str(),
            self.inner.requirement.enforceable_floor_mm(),
            self.inner.requirement.is_determinable(),
        )
    }
}

/// Python-visible [`Resolution`].
#[cfg(feature = "python")]
#[pyclass(frozen, skip_from_py_object, name = "InsulationResolution")]
#[derive(Clone, Debug)]
pub struct PyInsulationResolution {
    inner: Resolution,
}

#[cfg(feature = "python")]
#[pymethods]
impl PyInsulationResolution {
    fn pollution_degree(&self) -> u8 {
        match self.inner.pollution_degree {
            PollutionDegree::PD1 => 1,
            PollutionDegree::PD2 => 2,
            PollutionDegree::PD3 => 3,
        }
    }

    fn material_group(&self) -> String {
        self.inner.material_group.to_string()
    }

    /// Every pairing, in stable order.
    fn pairings(&self) -> Vec<PyInsulationPairing> {
        self.inner
            .pairings
            .iter()
            .cloned()
            .map(|inner| PyInsulationPairing { inner })
            .collect()
    }

    /// The pairing for two group names, in either order, or `None`.
    fn pairing(&self, a: &str, b: &str) -> Option<PyInsulationPairing> {
        self.inner
            .pairing(a, b)
            .cloned()
            .map(|inner| PyInsulationPairing { inner })
    }

    /// The pairing for two NET names, in either order, or `None` when either
    /// net is not declared. `None` is not "no requirement" -- see
    /// `Resolution::group_of`'s docstring.
    fn pairing_for_nets(&self, net_a: &str, net_b: &str) -> Option<PyInsulationPairing> {
        self.inner
            .pairing_for_nets(net_a, net_b)
            .cloned()
            .map(|inner| PyInsulationPairing { inner })
    }

    fn group_of(&self, net: &str) -> Option<String> {
        self.inner.group_of(net).map(str::to_string)
    }

    /// Every declared net -> its group name.
    fn declared_nets(&self) -> BTreeMap<String, String> {
        self.inner
            .declared_nets()
            .into_iter()
            .map(|(net, group)| (net.to_string(), group.to_string()))
            .collect()
    }

    /// The worst enforceable floor over every barrier-crossing pairing -- the
    /// figure a single geometric HV<->SELV barrier must be sized by.
    fn barrier_floor_mm(&self) -> f64 {
        self.inner.barrier_floor_mm()
    }

    /// `False` when any barrier-crossing pairing is indeterminate. Barrier
    /// compliance cannot be asserted while this is `False`.
    fn barrier_is_determinable(&self) -> bool {
        self.inner.barrier_is_determinable()
    }

    /// The pairing that sets `barrier_floor_mm()`.
    fn barrier_governing_pairing(&self) -> Option<PyInsulationPairing> {
        self.inner
            .barrier_governing_pairing()
            .cloned()
            .map(|inner| PyInsulationPairing { inner })
    }

    fn indeterminate_pairings(&self) -> Vec<PyInsulationPairing> {
        self.inner
            .indeterminate_pairings()
            .into_iter()
            .cloned()
            .map(|inner| PyInsulationPairing { inner })
            .collect()
    }

    fn verified_on(&self) -> &str {
        &self.inner.verified_on
    }

    fn measured_at_commit(&self) -> &str {
        &self.inner.measured_at_commit
    }

    /// The honest limit on what any of this proves.
    fn limitation(&self) -> &'static str {
        LIMITATION
    }

    fn __repr__(&self) -> String {
        format!(
            "InsulationResolution(pd={}, pairings={}, barrier_floor_mm={}, barrier_determinable={})",
            self.pollution_degree(),
            self.inner.pairings.len(),
            self.inner.barrier_floor_mm(),
            self.inner.barrier_is_determinable(),
        )
    }
}

/// Parse, validate and evaluate an insulation declaration.
///
/// Raises `ValueError` -- never returns a fallback -- on an empty,
/// unparseable, wrong-schema, placeholder, malformed-commit, stale,
/// incomplete or out-of-table declaration.
#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(signature = (yaml_text, pollution_degree))]
fn resolve_insulation_declaration(
    yaml_text: &str,
    pollution_degree: u8,
) -> PyResult<PyInsulationResolution> {
    match resolve(yaml_text, pollution_degree) {
        Ok(inner) => Ok(PyInsulationResolution { inner }),
        Err(e) => Err(PyValueError::new_err(e.to_string())),
    }
}

/// The canonical digest of a declaration's `groups:` + `pairings:` blocks --
/// the value that belongs in `verification.declared_state_sha256`.
///
/// Takes the whole document and re-parses it rather than taking the facts
/// piecemeal, so the digest a human is told to paste in is always computed
/// from exactly the bytes they committed.
#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(signature = (yaml_text))]
fn insulation_facts_digest(yaml_text: &str) -> PyResult<String> {
    #[derive(Deserialize)]
    struct FactsOnly {
        groups: BTreeMap<String, GroupFacts>,
        pairings: Vec<PairingFacts>,
    }
    let parsed: FactsOnly =
        serde_yaml::from_str(yaml_text).map_err(|e| PyValueError::new_err(e.to_string()))?;
    Ok(canonical_facts_digest(&parsed.groups, &parsed.pairings))
}

/// The required creepage for one (class, working voltage, frequency,
/// pollution degree) tuple, with no declaration around it.
///
/// Returns `(requirement_mm_or_nan, enforceable_floor_mm, is_determinable,
/// table, row, provenance)`. Exposed for differential and property testing of
/// the rule itself; production callers go through
/// `resolve_insulation_declaration`, which is the only path that also
/// enforces completeness and staleness.
#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(signature = (insulation, working_voltage_vrms, frequency_hz, pollution_degree))]
fn insulation_required_creepage(
    insulation: &str,
    working_voltage_vrms: f64,
    frequency_hz: f64,
    pollution_degree: u8,
) -> PyResult<(f64, f64, bool, &'static str, &'static str, String)> {
    let class = match insulation {
        "reinforced" => InsulationClass::Reinforced,
        "functional" => InsulationClass::Functional,
        other => {
            return Err(PyValueError::new_err(format!(
                "unknown insulation class {other:?}: expected 'reinforced' or 'functional'"
            )))
        }
    };
    let pd = PollutionDegree::from_u8(pollution_degree)
        .ok_or_else(|| PyValueError::new_err(format!("bad pollution degree {pollution_degree}")))?;
    let range = voltage_range_for(working_voltage_vrms).ok_or_else(|| {
        PyValueError::new_err(format!(
            "working voltage {working_voltage_vrms} V is above the highest transcribed table row"
        ))
    })?;
    let req = required_creepage(class, working_voltage_vrms, frequency_hz, pd).ok_or_else(|| {
        PyValueError::new_err(format!(
            "no recovered {} cell for ({pd}, {MATERIAL_GROUP}, {range})",
            class.table_name()
        ))
    })?;
    Ok((
        req.requirement_mm(),
        req.enforceable_floor_mm(),
        req.is_determinable(),
        class.table_name(),
        range.as_str(),
        req.provenance_debug(),
    ))
}

/// IEC 60664-1 cl. 1.1.1's scope ceiling, in Hz. Exposed so a gate can print
/// the number it is comparing against without holding a second copy of it.
#[cfg(feature = "python")]
#[pyfunction]
fn insulation_frequency_scope_ceiling_hz() -> f64 {
    FREQUENCY_SCOPE_CEILING_HZ
}

/// The honest limit, as a module-level function Python can read.
#[cfg(feature = "python")]
#[pyfunction]
fn insulation_mechanism_limitation() -> &'static str {
    LIMITATION
}

/// Register the insulation surface on the `temper_design_bundle_python`
/// module.
#[cfg(feature = "python")]
pub fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<PyInsulationPairing>()?;
    module.add_class::<PyInsulationResolution>()?;
    module.add_function(wrap_pyfunction!(resolve_insulation_declaration, module)?)?;
    module.add_function(wrap_pyfunction!(insulation_facts_digest, module)?)?;
    module.add_function(wrap_pyfunction!(insulation_required_creepage, module)?)?;
    module.add_function(wrap_pyfunction!(
        insulation_frequency_scope_ceiling_hz,
        module
    )?)?;
    module.add_function(wrap_pyfunction!(insulation_mechanism_limitation, module)?)?;
    Ok(())
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

    const GOOD_COMMIT: &str = "0cbc04248d772cc3dfb66799f519d3a2a45a6de1";

    /// A two-group declaration (one HV, one SELV) with the three required
    /// pairings, digest filled in.
    fn manifest(hv_freq: f64, hv_selv_v: f64) -> String {
        let mut groups: BTreeMap<String, GroupFacts> = BTreeMap::new();
        groups.insert(
            "BUS".to_string(),
            GroupFacts {
                domain: Domain::Hv,
                nets: vec!["+170V_BUS".to_string()],
                frequency_hz: hv_freq,
                basis: "test".to_string(),
            },
        );
        groups.insert(
            "SELV".to_string(),
            GroupFacts {
                domain: Domain::Selv,
                nets: vec!["gnd".to_string()],
                frequency_hz: 0.0,
                basis: "test".to_string(),
            },
        );
        let pairings = vec![
            PairingFacts {
                a: "BUS".to_string(),
                b: "SELV".to_string(),
                working_voltage_vrms: hv_selv_v,
                basis: "test".to_string(),
            },
            PairingFacts {
                a: "BUS".to_string(),
                b: "BUS".to_string(),
                working_voltage_vrms: 340.0,
                basis: "test".to_string(),
            },
            PairingFacts {
                a: "SELV".to_string(),
                b: "SELV".to_string(),
                working_voltage_vrms: 15.0,
                basis: "test".to_string(),
            },
        ];
        let digest = canonical_facts_digest(&groups, &pairings);
        format!(
            r#"
schema_version: 1
groups:
  BUS:
    domain: HV
    nets: ["+170V_BUS"]
    frequency_hz: {hv_freq}
    basis: test
  SELV:
    domain: SELV
    nets: ["gnd"]
    frequency_hz: 0.0
    basis: test
pairings:
  - {{a: BUS, b: SELV, working_voltage_vrms: {hv_selv_v}, basis: test}}
  - {{a: BUS, b: BUS, working_voltage_vrms: 340.0, basis: test}}
  - {{a: SELV, b: SELV, working_voltage_vrms: 15.0, basis: test}}
verification:
  verified_on: "2026-08-19"
  verified_by: test
  method: test
  measured_at_commit: "{GOOD_COMMIT}"
  artifacts: ["docs/evidence/x.md"]
  declared_state_sha256: "{digest}"
"#
        )
    }

    // -- the rule ---------------------------------------------------------

    pub fn voltage_ladder_is_inclusive_at_the_top() {
        assert_eq!(voltage_range_for(50.0), Some(VoltageRange::UpTo50));
        assert_eq!(voltage_range_for(50.001), Some(VoltageRange::Gt50Le125));
        assert_eq!(voltage_range_for(120.0), Some(VoltageRange::Gt50Le125));
        assert_eq!(voltage_range_for(125.0), Some(VoltageRange::Gt50Le125));
        assert_eq!(voltage_range_for(125.001), Some(VoltageRange::Gt125Le250));
        assert_eq!(voltage_range_for(170.0), Some(VoltageRange::Gt125Le250));
        assert_eq!(voltage_range_for(208.1), Some(VoltageRange::Gt125Le250));
        assert_eq!(voltage_range_for(250.0), Some(VoltageRange::Gt125Le250));
        assert_eq!(voltage_range_for(340.0), Some(VoltageRange::Gt250Le400));
        assert_eq!(voltage_range_for(570.5), Some(VoltageRange::Gt500Le800));
        // Never saturates.
        assert_eq!(voltage_range_for(12_500.0), Some(VoltageRange::Gt10000Le12500));
        assert_eq!(voltage_range_for(12_500.1), None);
    }

    /// The five figures the 2026-08-19 determination names, each reproduced
    /// from the recovered tables through this module's own rule.
    pub fn determination_table_reproduces() {
        let pd = PollutionDegree::PD3;
        // Mains <-> SELV: 120 V, reinforced, T17 row ii (2.4) x2.
        let mains = required_creepage(InsulationClass::Reinforced, 120.0, 60.0, pd).unwrap();
        assert!(mains.is_determinable());
        assert!((mains.requirement_mm() - 4.8).abs() < 1e-9, "{mains:?}");
        // DC bus <-> SELV: 170 V d.c., reinforced, T17 row iii (4.0) x2.
        let bus = required_creepage(InsulationClass::Reinforced, 170.0, 0.0, pd).unwrap();
        assert!(bus.is_determinable());
        assert!((bus.requirement_mm() - 8.0).abs() < 1e-9, "{bus:?}");
        // The propagating r.m.s. reading lands in the same row.
        let bus_rms = required_creepage(InsulationClass::Reinforced, 208.1, 0.0, pd).unwrap();
        assert!((bus_rms.requirement_mm() - 8.0).abs() < 1e-9);
        // Rail-to-rail: 340 V d.c., FUNCTIONAL, T18 row iii, UNDOUBLED.
        let rail = required_creepage(InsulationClass::Functional, 340.0, 0.0, pd).unwrap();
        assert!(rail.is_determinable());
        assert!((rail.requirement_mm() - 5.0).abs() < 1e-9, "{rail:?}");
        // Tank <-> SELV: 570.5 V @ 47 kHz, reinforced, T17 row vi (10.0) x2
        // as a FLOOR, requirement NOT determinable.
        let tank = required_creepage(InsulationClass::Reinforced, 570.5, 47_000.0, pd).unwrap();
        assert!(!tank.is_determinable());
        assert!(tank.requirement_mm().is_nan());
        assert!((tank.enforceable_floor_mm() - 20.0).abs() < 1e-9, "{tank:?}");
        // Tank <-> bus: functional, T18 row v (10.0), also above the ceiling.
        let tank_bus = required_creepage(InsulationClass::Functional, 570.5, 47_000.0, pd).unwrap();
        assert!(!tank_bus.is_determinable());
        assert!((tank_bus.enforceable_floor_mm() - 10.0).abs() < 1e-9);
    }

    /// 12.6 mm is Table 17 row **iv** doubled, and no pairing this design
    /// actually has lands there. The regression this whole module exists to
    /// prevent is a pairing silently reverting to it.
    pub fn twelve_point_six_is_row_iv_and_unreachable_from_this_design() {
        let pd = PollutionDegree::PD3;
        let row_iv = required_creepage(InsulationClass::Reinforced, 400.0, 0.0, pd).unwrap();
        assert!((row_iv.requirement_mm() - 12.6).abs() < 1e-9);
        // Every working voltage this design declares against SELV is either
        // below row iv or above it -- never in it.
        for v in [120.0_f64, 170.0, 208.1, 570.5] {
            let got = required_creepage(InsulationClass::Reinforced, v, 0.0, pd)
                .unwrap()
                .enforceable_floor_mm();
            assert!(
                (got - 12.6).abs() > 1e-9,
                "working voltage {v} V must not produce the row-iv figure, got {got}"
            );
        }
    }

    pub fn frequency_ceiling_is_thirty_kilohertz_inclusive() {
        assert!(frequency_in_scope(0.0));
        assert!(frequency_in_scope(60.0));
        assert!(frequency_in_scope(30_000.0));
        assert!(!frequency_in_scope(30_000.1));
        assert!(!frequency_in_scope(47_000.0));
    }

    /// An indeterminate requirement must never yield a number, and must never
    /// grade as a pass -- at ANY measured distance, including absurdly large
    /// ones.
    pub fn indeterminate_never_passes_at_any_distance() {
        let req =
            required_creepage(InsulationClass::Reinforced, 570.5, 47_000.0, PollutionDegree::PD3)
                .unwrap();
        assert!(req.requirement_mm().is_nan());
        for measured in [0.0_f64, 9.1, 12.6, 19.999, 20.0, 100.0, 1.0e9] {
            let verdict = req.grade(measured);
            assert!(!verdict.is_pass(), "{measured} mm graded {verdict:?}");
            assert_eq!(
                verdict,
                if measured >= 20.0 {
                    Verdict::Indeterminate
                } else {
                    Verdict::Fail
                },
                "measured {measured}"
            );
        }
    }

    /// A NaN measurement must FAIL, not pass by accident.
    pub fn nan_measurement_fails() {
        let det =
            required_creepage(InsulationClass::Reinforced, 170.0, 0.0, PollutionDegree::PD3)
                .unwrap();
        assert_eq!(det.grade(f64::NAN), Verdict::Fail);
        assert_eq!(det.grade(8.0), Verdict::Pass);
        assert_eq!(det.grade(7.999), Verdict::Fail);
    }

    pub fn insulation_class_is_derived_from_domains() {
        assert_eq!(
            insulation_class_for(Domain::Hv, Domain::Selv),
            InsulationClass::Reinforced
        );
        assert_eq!(
            insulation_class_for(Domain::Selv, Domain::Hv),
            InsulationClass::Reinforced
        );
        assert_eq!(
            insulation_class_for(Domain::Hv, Domain::Hv),
            InsulationClass::Functional
        );
        assert_eq!(
            insulation_class_for(Domain::Selv, Domain::Selv),
            InsulationClass::Functional
        );
    }

    /// Reinforced is never cheaper than functional at the same voltage --
    /// a monotonicity the tables satisfy and a doubling bug would break.
    pub fn reinforced_is_never_below_functional() {
        for v in [15.0_f64, 120.0, 170.0, 340.0, 480.0, 570.5, 900.0] {
            let r = required_creepage(InsulationClass::Reinforced, v, 0.0, PollutionDegree::PD3)
                .unwrap()
                .enforceable_floor_mm();
            let f = required_creepage(InsulationClass::Functional, v, 0.0, PollutionDegree::PD3)
                .unwrap()
                .enforceable_floor_mm();
            assert!(r >= f, "at {v} V reinforced {r} < functional {f}");
        }
    }

    /// PD3 is never cheaper than PD2, at any voltage or class.
    pub fn pd3_is_never_below_pd2() {
        for v in [15.0_f64, 120.0, 170.0, 340.0, 570.5] {
            for class in [InsulationClass::Reinforced, InsulationClass::Functional] {
                let pd2 = required_creepage(class, v, 0.0, PollutionDegree::PD2)
                    .unwrap()
                    .enforceable_floor_mm();
                let pd3 = required_creepage(class, v, 0.0, PollutionDegree::PD3)
                    .unwrap()
                    .enforceable_floor_mm();
                assert!(pd3 >= pd2, "{class:?} at {v} V: PD3 {pd3} < PD2 {pd2}");
            }
        }
    }

    // -- the declaration --------------------------------------------------

    pub fn good_declaration_resolves() {
        let r = resolve(&manifest(0.0, 170.0), 3).unwrap();
        assert_eq!(r.pairings.len(), 3);
        assert!(r.barrier_is_determinable());
        assert!((r.barrier_floor_mm() - 8.0).abs() < 1e-9);
        assert_eq!(r.group_of("+170V_BUS"), Some("BUS"));
        assert_eq!(r.group_of("gnd"), Some("SELV"));
        assert_eq!(r.group_of("not-a-net"), None);
        let p = r.pairing_for_nets("+170V_BUS", "gnd").unwrap();
        assert_eq!(p.insulation, InsulationClass::Reinforced);
        assert!(p.crosses_barrier());
        // Order-insensitive.
        assert_eq!(r.pairing_for_nets("gnd", "+170V_BUS"), Some(p));
    }

    /// The barrier's governing figure is the WORST crossing, not the DC bus
    /// one -- the finding this module exists to implement.
    pub fn barrier_floor_is_the_worst_crossing_and_carries_indeterminacy() {
        let r = resolve(&manifest(47_000.0, 570.5), 3).unwrap();
        assert!((r.barrier_floor_mm() - 20.0).abs() < 1e-9);
        assert!(!r.barrier_is_determinable());
        assert_eq!(r.indeterminate_pairings().len(), 2); // BUS<->SELV, BUS<->BUS
        assert_eq!(r.barrier_governing_pairing().unwrap().group_a, "BUS");
    }

    pub fn empty_is_rejected() {
        assert_eq!(resolve("   \n", 3), Err(DeclarationError::Empty));
    }

    pub fn bad_pollution_degree_is_rejected() {
        assert_eq!(
            resolve(&manifest(0.0, 170.0), 4),
            Err(DeclarationError::BadPollutionDegree { found: 4 })
        );
    }

    pub fn unsupported_schema_version_is_rejected() {
        let doc = manifest(0.0, 170.0).replace("schema_version: 1", "schema_version: 99");
        assert_eq!(
            resolve(&doc, 3),
            Err(DeclarationError::UnsupportedSchemaVersion { found: 99 })
        );
    }

    pub fn unknown_key_is_rejected() {
        let doc = manifest(0.0, 170.0).replace(
            "schema_version: 1",
            "schema_version: 1\npollution_degree: 2",
        );
        assert!(matches!(
            resolve(&doc, 3),
            Err(DeclarationError::Unparseable(_))
        ));
    }

    /// Editing a working voltage without re-verifying is STALE, not accepted.
    pub fn edited_working_voltage_is_stale() {
        let doc = manifest(0.0, 170.0).replace("working_voltage_vrms: 170", "working_voltage_vrms: 120");
        match resolve(&doc, 3) {
            Err(DeclarationError::StaleDeclaration { .. }) => {}
            other => panic!("expected StaleDeclaration, got {other:?}"),
        }
    }

    /// Moving a net between groups is STALE too -- the digest covers
    /// membership, not just numbers.
    pub fn moved_net_is_stale() {
        let doc = manifest(0.0, 170.0).replace(r#"nets: ["+170V_BUS"]"#, r#"nets: ["SW_NODE"]"#);
        match resolve(&doc, 3) {
            Err(DeclarationError::StaleDeclaration { .. }) => {}
            other => panic!("expected StaleDeclaration, got {other:?}"),
        }
    }

    pub fn placeholder_verification_is_rejected() {
        let doc = manifest(0.0, 170.0).replace("verified_by: test", "verified_by: TBD");
        match resolve(&doc, 3) {
            Err(DeclarationError::PlaceholderField { field, .. }) => {
                assert_eq!(field, "verified_by")
            }
            other => panic!("expected PlaceholderField, got {other:?}"),
        }
    }

    pub fn malformed_commit_is_rejected() {
        let doc = manifest(0.0, 170.0).replace(GOOD_COMMIT, "deadbeef");
        match resolve(&doc, 3) {
            Err(DeclarationError::MalformedVerificationCommit { .. }) => {}
            other => panic!("expected MalformedVerificationCommit, got {other:?}"),
        }
    }

    /// A missing pairing is a hard error, never a default. This is the
    /// property that stops a newly-added group from silently inheriting some
    /// other pairing's number.
    pub fn missing_pairing_is_rejected() {
        let doc = manifest(0.0, 170.0)
            .lines()
            .filter(|l| !l.contains("a: SELV, b: SELV"))
            .collect::<Vec<_>>()
            .join("\n");
        // The digest no longer matches either, so re-derive: build the
        // declaration with the pairing removed from BOTH the doc and the
        // digest input.
        let mut groups: BTreeMap<String, GroupFacts> = BTreeMap::new();
        groups.insert(
            "BUS".to_string(),
            GroupFacts {
                domain: Domain::Hv,
                nets: vec!["+170V_BUS".to_string()],
                frequency_hz: 0.0,
                basis: "test".to_string(),
            },
        );
        groups.insert(
            "SELV".to_string(),
            GroupFacts {
                domain: Domain::Selv,
                nets: vec!["gnd".to_string()],
                frequency_hz: 0.0,
                basis: "test".to_string(),
            },
        );
        let pairings = vec![
            PairingFacts {
                a: "BUS".to_string(),
                b: "SELV".to_string(),
                working_voltage_vrms: 170.0,
                basis: "test".to_string(),
            },
            PairingFacts {
                a: "BUS".to_string(),
                b: "BUS".to_string(),
                working_voltage_vrms: 340.0,
                basis: "test".to_string(),
            },
        ];
        let digest = canonical_facts_digest(&groups, &pairings);
        let old_digest = canonical_facts_digest(
            &groups,
            &[
                pairings[0].clone(),
                pairings[1].clone(),
                PairingFacts {
                    a: "SELV".to_string(),
                    b: "SELV".to_string(),
                    working_voltage_vrms: 15.0,
                    basis: "test".to_string(),
                },
            ],
        );
        let doc = doc.replace(&old_digest, &digest);
        match resolve(&doc, 3) {
            Err(DeclarationError::MissingPairing { a, b }) => {
                assert_eq!((a.as_str(), b.as_str()), ("SELV", "SELV"));
            }
            other => panic!("expected MissingPairing, got {other:?}"),
        }
    }

    pub fn digest_ignores_comments_and_key_order() {
        let doc = manifest(0.0, 170.0);
        let with_comments = doc.replace("groups:", "# a comment\ngroups:");
        assert!(resolve(&with_comments, 3).is_ok());
    }

    /// `basis` is part of the digest: the justification of a safety number is
    /// part of the claim.
    pub fn changing_a_basis_is_stale() {
        let doc = manifest(0.0, 170.0).replacen(
            "- {a: BUS, b: SELV, working_voltage_vrms: 170, basis: test}",
            "- {a: BUS, b: SELV, working_voltage_vrms: 170, basis: something-else}",
            1,
        );
        // The replacen only fires if the rendering matches; guard so the test
        // is never vacuous.
        assert!(doc.contains("something-else"), "fixture text drifted");
        match resolve(&doc, 3) {
            Err(DeclarationError::StaleDeclaration { .. }) => {}
            other => panic!("expected StaleDeclaration, got {other:?}"),
        }
    }

    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("insulation::voltage_ladder_is_inclusive_at_the_top", voltage_ladder_is_inclusive_at_the_top),
        ("insulation::determination_table_reproduces", determination_table_reproduces),
        ("insulation::twelve_point_six_is_row_iv_and_unreachable_from_this_design", twelve_point_six_is_row_iv_and_unreachable_from_this_design),
        ("insulation::frequency_ceiling_is_thirty_kilohertz_inclusive", frequency_ceiling_is_thirty_kilohertz_inclusive),
        ("insulation::indeterminate_never_passes_at_any_distance", indeterminate_never_passes_at_any_distance),
        ("insulation::nan_measurement_fails", nan_measurement_fails),
        ("insulation::insulation_class_is_derived_from_domains", insulation_class_is_derived_from_domains),
        ("insulation::reinforced_is_never_below_functional", reinforced_is_never_below_functional),
        ("insulation::pd3_is_never_below_pd2", pd3_is_never_below_pd2),
        ("insulation::good_declaration_resolves", good_declaration_resolves),
        ("insulation::barrier_floor_is_the_worst_crossing_and_carries_indeterminacy", barrier_floor_is_the_worst_crossing_and_carries_indeterminacy),
        ("insulation::empty_is_rejected", empty_is_rejected),
        ("insulation::bad_pollution_degree_is_rejected", bad_pollution_degree_is_rejected),
        ("insulation::unsupported_schema_version_is_rejected", unsupported_schema_version_is_rejected),
        ("insulation::unknown_key_is_rejected", unknown_key_is_rejected),
        ("insulation::edited_working_voltage_is_stale", edited_working_voltage_is_stale),
        ("insulation::moved_net_is_stale", moved_net_is_stale),
        ("insulation::placeholder_verification_is_rejected", placeholder_verification_is_rejected),
        ("insulation::malformed_commit_is_rejected", malformed_commit_is_rejected),
        ("insulation::missing_pairing_is_rejected", missing_pairing_is_rejected),
        ("insulation::digest_ignores_comments_and_key_order", digest_ignores_comments_and_key_order),
        ("insulation::changing_a_basis_is_stale", changing_a_basis_is_stale),
    ];

    #[test]
    fn run_wasm_tests() {
        for (name, f) in WASM_TESTS {
            eprintln!("running {name}");
            f();
        }
    }
}
