//! Safety-critical values with provenance — the typed home for every
//! clearance/creepage number this project relies on.
//!
//! ## Why this module exists
//!
//! The 2026-08-15 safety-assertion audit (handoff §3) found that roughly one
//! in seven safety assertions in this repo traces to a specification; the
//! rest are MISCITED (a citation that does not support the number), SNAPSHOT
//! (the number exists only in test+code), or worse. The canonical case is
//! `14.0` mm (HIGH_VOLTAGE creepage base): introduced with a bare
//! "IEC 60335-1 Table 17" comment and not traceable to any recovered table
//! row applicable to this board (see
//! `docs/evidence/2026-08-15-creepage-base-14-verification.md`).
//!
//! This module defines [`SafetyValue`] — a value plus the [`Standard`] it
//! traces to and the [`Provenance`] of how it was obtained — and encodes the
//! *recovered* primary tables verbatim:
//!
//! | Table | Recovered in | Content |
//! |---|---|---|
//! | Table 16 | [`DOC_CREEPAGE_BRAINSTORM`] §3.2 | minimum clearances (cl. 29.1.3) |
//! | Table 17 | [`DOC_CREEPAGE_BRAINSTORM`] §3.3 | basic-insulation creepage, rows i–vii (cl. 29.2.1) |
//! | Table 18 | [`DOC_HV_HV_CREEPAGE`] §3.1 | functional-insulation creepage, full 18 rows (cl. 29.2.4) |
//!
//! All three are CITED-PRIMARY transcriptions of IS 302-1:2008 (the BIS
//! identical adoption of IEC 60335-1), recovered from an OCR'd scan and
//! cross-checked cell-for-cell against Broadcom's IEC 60664-1 reproduction
//! (Table 17) or against the same artifact's clause text (Table 18). The
//! transcription rules are the project's: **never invent or reconstruct a
//! standards value** — every number below is quoted from a recovered table,
//! and where the answer is "not obtainable", that is the answer (see
//! [`unobtainable`]).
//!
//! ## The "Table 9" discrepancy (read before editing)
//!
//! The 2026-08-15 handoff says "IEC 60335-1 Table 9 was recovered verbatim".
//! That is **not** a clearance table: the recovered primary text
//! (IS 302-1:2008) numbers the clearance table **Table 16** (cl. 29.1.4:
//! "the values of Table 16 are applicable"; cl. 29.2.1: "the minimum
//! dimension specified for the clearance of Table 16"), and the only
//! "Table 9" in the recovered artifact is the **temperature-rise** table
//! (cl. 11.8, referenced by cl. 19.13), which no evidence doc transcribes.
//! The clearance table encoded here is therefore **Table 16**; a
//! [`table_9_temperature_rise`] marker is provided as `Unobtainable` so the
//! gap is representable rather than silent.
//!
//! ## Design notes
//!
//! - **No serde derives, deliberately.** These types are compile-time
//!   constants and trusted-code constructions. Deserializing a `SafetyValue`
//!   would let untrusted data *claim* provenance; the absence of
//!   `Deserialize` is the point.
//! - **`RecoveredPrimary` cells are `const`.** Every cell of Table 16/17/18
//!   is a `const` value carrying its full provenance in `&'static str`
//!   fields, so the tables are auditable data, greppable per value.
//! - **`Derived` values carry their `from` value.** `creepage_reinforced`
//!   and the named `reinforced_*` constructors box the exact basic cell they
//!   double, so the derivation chain is inspectable.
//! - **`Fabricated` is a label, not a value.** The legacy `14.0` and its
//!   siblings are encoded so migration can *name* what it is replacing.
//!   Production paths must gate on [`SafetyValue::is_fabricated`] and refuse
//!   fabricated values; this module provides no production caller for them.
//!
//! The pyo3 surface (`PySafetyValue`, `creepage_table_lookup`,
//! `clearance_table_lookup`) is `#[cfg(feature = "python")]`-gated; the core
//! types and tables compile in `--no-default-features` builds (and onto the
//! wasm32 tier).

use std::fmt;
use std::str::FromStr;

// ---------------------------------------------------------------------------
// Evidence documents (stable paths; line refs in the table comments below)
// ---------------------------------------------------------------------------

/// The recovered Table 16 + Table 17 source: CITED-PRIMARY, IS 302-1:2008.
/// Table 16 at §3.2 (lines ~255-268), Table 17 at §3.3 (lines ~286-294).
pub const DOC_CREEPAGE_BRAINSTORM: &str =
    "docs/evidence/2026-07-28-creepage-determination-brainstorm.md";

/// The recovered Table 18 source: CITED-PRIMARY, same IS 302-1:2008 artifact,
/// transcribed in full at §3.1 (lines ~188-207), sha256 recorded in the doc's
/// provenance header.
pub const DOC_HV_HV_CREEPAGE: &str = "docs/evidence/2026-08-12-hv-hv-creepage-determination.md";

/// The 14.0-mm verification report: proves the value is not traceable to any
/// recovered table row applicable to this board, and identifies the origin
/// commit `418fab757`.
pub const DOC_CREEPAGE_BASE_14_VERIFICATION: &str =
    "docs/evidence/2026-08-15-creepage-base-14-verification.md";

// ---------------------------------------------------------------------------
// Standard
// ---------------------------------------------------------------------------

/// The standard a value traces to.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
// Variant names follow the task specification verbatim (IEC 60335-1 etc.);
// the all-caps acronyms are the API surface.
#[allow(clippy::upper_case_acronyms)]
pub enum Standard {
    /// IEC 60335-1 — Table 16 (clearance), Table 17 (creepage, basic),
    /// Table 18 (creepage, functional).
    IEC60335_1,
    /// IEC 60664-1 — insulation coordination.
    IEC60664_1,
    /// IPC-2221B — current capacity.
    IPC2221B,
    /// IEC 60664-4 — frequency-dependent insulation (paywalled; values are
    /// `Unobtainable` in this repo).
    IEC60664_4,
    /// IEC 60950-1 — ITE safety (withdrawn; superseded by IEC 62368-1).
    IEC60950_1,
    /// IEC 62368-1 — audio/video, information and communication technology
    /// equipment.
    IEC62368_1,
}

// ---------------------------------------------------------------------------
// Provenance
// ---------------------------------------------------------------------------

/// How a [`SafetyValue`] was obtained — the whole point of the type.
#[derive(Debug, Clone, PartialEq)]
pub enum Provenance {
    /// Verbatim transcription of a recovered primary-source table.
    RecoveredPrimary {
        /// Path to the evidence doc, e.g.
        /// `docs/evidence/2026-07-28-creepage-determination-brainstorm.md`.
        doc: &'static str,
        /// e.g. `"Table 17"`, `"Table 9"`.
        table: &'static str,
        /// e.g. `"row iv (>250-400 V), PD2, group IIIa/IIIb"`.
        row: &'static str,
        /// The clause permitting the value, e.g. `"29.2.1"`.
        clause: &'static str,
    },
    /// Derived from another [`SafetyValue`] via a documented formula.
    Derived {
        from: Box<SafetyValue>,
        /// e.g. `"6.3 x 2 = 12.6 (clause 29.2.3)"`.
        formula: &'static str,
        /// The clause permitting the derivation, e.g. `"29.2.3"`.
        clause: &'static str,
    },
    /// Measured from a specific board state.
    Measured {
        commit: &'static str,
        samples: usize,
        /// e.g. `"kicad-cli 10.0.5"`.
        tool: &'static str,
    },
    /// Explicitly "we don't know" — the standard is paywalled or the case is
    /// not covered by any recovered text. `value_mm()` is `NaN`; gate on
    /// [`SafetyValue::is_unobtainable`] before arithmetic.
    Unobtainable { reason: &'static str },
    /// Known-fabricated — exists ONLY to label existing unsourced values
    /// during migration. Production paths must refuse values whose
    /// [`SafetyValue::is_fabricated`] is true (the CI analogue would be a
    /// grep gate that fails if a `Fabricated` value is used off the legacy
    /// path).
    Fabricated {
        /// Commit that first introduced the value.
        origin_commit: &'static str,
        /// Why it is fabricated.
        note: &'static str,
    },
}

// ---------------------------------------------------------------------------
// SafetyValue
// ---------------------------------------------------------------------------

/// A safety-critical value that carries its own provenance.
///
/// Construction is trusted-code-only (no `Deserialize`): a value that cannot
/// name where it came from cannot be represented here — use
/// [`unobtainable`] instead of inventing one.
#[derive(Debug, Clone, PartialEq)]
pub struct SafetyValue {
    value_mm: f64,
    standard: Standard,
    provenance: Provenance,
}

impl SafetyValue {
    /// The value in millimetres. `NaN` when `is_unobtainable()`.
    pub fn value_mm(&self) -> f64 {
        self.value_mm
    }

    /// The standard this value traces to.
    pub fn standard(&self) -> Standard {
        self.standard
    }

    /// The full provenance record.
    pub fn provenance(&self) -> &Provenance {
        &self.provenance
    }

    /// True when this value is a known-fabricated legacy label.
    pub fn is_fabricated(&self) -> bool {
        matches!(self.provenance, Provenance::Fabricated { .. })
    }

    /// True when this value is explicitly unknown (paywalled standard,
    /// untranscribed table, uncovered case). `value_mm()` is `NaN`.
    pub fn is_unobtainable(&self) -> bool {
        matches!(self.provenance, Provenance::Unobtainable { .. })
    }

    /// Human-readable one-line provenance description (used by the pyo3
    /// `provenance_debug()` binding and by tests).
    pub fn provenance_debug(&self) -> String {
        match &self.provenance {
            Provenance::RecoveredPrimary { doc, table, row, clause } => format!(
                "RecoveredPrimary: {table}, {row} (clause {clause}) — {doc}"
            ),
            Provenance::Derived { from, formula, clause } => format!(
                "Derived: {formula} from {} mm (clause {clause})",
                from.value_mm()
            ),
            Provenance::Measured { commit, samples, tool } => {
                format!("Measured: {samples} samples with {tool} at commit {commit}")
            }
            Provenance::Unobtainable { reason } => format!("Unobtainable: {reason}"),
            Provenance::Fabricated { origin_commit, note } => {
                format!("FABRICATED: {note} (origin commit {origin_commit})")
            }
        }
    }
}

/// Construct an explicitly-unknown value. `value_mm()` is `NaN`; consumers
/// must gate on [`SafetyValue::is_unobtainable`] before arithmetic.
pub fn unobtainable(standard: Standard, reason: &'static str) -> SafetyValue {
    SafetyValue {
        value_mm: f64::NAN,
        standard,
        provenance: Provenance::Unobtainable { reason },
    }
}

/// IEC 60664-4 frequency-dependent insulation values. Paywalled; no free
/// adoption route found (see the 2026-08-14 certification-lab package).
pub fn iec60664_4_frequency_dependent_creepage() -> SafetyValue {
    unobtainable(
        Standard::IEC60664_4,
        "IEC 60664-4 Annex L paywalled; no free adoption route found (docs/evidence/2026-08-14-certification-lab-package-pd3-and-60664-4.md)",
    )
}

/// IEC 60335-1 Table 9 (temperature rises, cl. 11.8) — the table the handoff
/// calls "recovered verbatim". It is *referenced* by cl. 19.13 in the
/// recovered text but **not transcribed** in any evidence doc; the recovered
/// clearance table is Table 16 (see the module docstring).
pub fn table_9_temperature_rise() -> SafetyValue {
    unobtainable(
        Standard::IEC60335_1,
        "IEC 60335-1 Table 9 (temperature rises, cl. 11.8) referenced by cl. 19.13 in recovered text but not transcribed in any docs/evidence doc; the recovered clearance table is Table 16",
    )
}

// ---------------------------------------------------------------------------
// Table keys
// ---------------------------------------------------------------------------

/// Pollution degree, as used by Table 17/18 columns and cl. 29.2.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum PollutionDegree {
    PD1,
    PD2,
    PD3,
}

impl PollutionDegree {
    pub fn from_u8(v: u8) -> Option<Self> {
        match v {
            1 => Some(Self::PD1),
            2 => Some(Self::PD2),
            3 => Some(Self::PD3),
            _ => None,
        }
    }
}

impl fmt::Display for PollutionDegree {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::PD1 => write!(f, "PD1"),
            Self::PD2 => write!(f, "PD2"),
            Self::PD3 => write!(f, "PD3"),
        }
    }
}

/// Material group (cl. 29.2): I = 600 < CTI, II = 400 < CTI < 600,
/// IIIa = 175 < CTI < 400, IIIb = 100 < CTI < 175. Table 17/18 **merge**
/// IIIa and IIIb into one column — the merged group is `IIIaOrIIIb`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum MaterialGroup {
    I,
    II,
    IIIaOrIIIb,
}

impl FromStr for MaterialGroup {
    type Err = String;

    fn from_str(s: &str) -> Result<Self, Self::Err> {
        match s {
            "I" | "group I" | "i" => Ok(Self::I),
            "II" | "group II" | "ii" => Ok(Self::II),
            // "IIIa" and "IIIb" resolve to the same merged column.
            "IIIa/IIIb" | "IIIa" | "IIIb" | "group IIIa/IIIb" | "iii" => Ok(Self::IIIaOrIIIb),
            _ => Err(format!("unknown material group '{s}'")),
        }
    }
}

impl fmt::Display for MaterialGroup {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::I => write!(f, "I"),
            Self::II => write!(f, "II"),
            Self::IIIaOrIIIb => write!(f, "IIIa/IIIb"),
        }
    }
}

/// Working-voltage (Table 17/18) or rated-impulse-voltage bracket.
///
/// Labels match the recovered tables' rows ("<=50", ">50-125", ...); the
/// `FromStr` impl accepts those canonical labels plus the long form used in
/// the evidence docs (">250 and <=400").
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum VoltageRange {
    UpTo50,
    Gt50Le125,
    Gt125Le250,
    Gt250Le400,
    Gt400Le500,
    Gt500Le800,
    Gt800Le1000,
    Gt1000Le1250,
    Gt1250Le1600,
    Gt1600Le2000,
    Gt2000Le2500,
    Gt2500Le3200,
    Gt3200Le4000,
    Gt4000Le5000,
    Gt5000Le6300,
    Gt6300Le8000,
    Gt8000Le10000,
    Gt10000Le12500,
}

impl VoltageRange {
    pub fn as_str(&self) -> &'static str {
        match self {
            Self::UpTo50 => "<=50",
            Self::Gt50Le125 => ">50-125",
            Self::Gt125Le250 => ">125-250",
            Self::Gt250Le400 => ">250-400",
            Self::Gt400Le500 => ">400-500",
            Self::Gt500Le800 => ">500-800",
            Self::Gt800Le1000 => ">800-1000",
            Self::Gt1000Le1250 => ">1000-1250",
            Self::Gt1250Le1600 => ">1250-1600",
            Self::Gt1600Le2000 => ">1600-2000",
            Self::Gt2000Le2500 => ">2000-2500",
            Self::Gt2500Le3200 => ">2500-3200",
            Self::Gt3200Le4000 => ">3200-4000",
            Self::Gt4000Le5000 => ">4000-5000",
            Self::Gt5000Le6300 => ">5000-6300",
            Self::Gt6300Le8000 => ">6300-8000",
            Self::Gt8000Le10000 => ">8000-10000",
            Self::Gt10000Le12500 => ">10000-12500",
        }
    }
}

impl FromStr for VoltageRange {
    type Err = String;

    fn from_str(s: &str) -> Result<Self, Self::Err> {
        // Canonical labels plus the evidence docs' long forms.
        match s {
            "<=50" | "<=50 V" => Ok(Self::UpTo50),
            ">50-125" | ">50 and <=125" => Ok(Self::Gt50Le125),
            ">125-250" | ">125 and <=250" => Ok(Self::Gt125Le250),
            ">250-400" | ">250 and <=400" => Ok(Self::Gt250Le400),
            ">400-500" | ">400 and <=500" => Ok(Self::Gt400Le500),
            ">500-800" | ">500 and <=800" => Ok(Self::Gt500Le800),
            ">800-1000" | ">800 and <=1000" => Ok(Self::Gt800Le1000),
            ">1000-1250" | ">1000 and <=1250" => Ok(Self::Gt1000Le1250),
            ">1250-1600" | ">1250 and <=1600" => Ok(Self::Gt1250Le1600),
            ">1600-2000" | ">1600 and <=2000" => Ok(Self::Gt1600Le2000),
            ">2000-2500" | ">2000 and <=2500" => Ok(Self::Gt2000Le2500),
            ">2500-3200" | ">2500 and <=3200" => Ok(Self::Gt2500Le3200),
            ">3200-4000" | ">3200 and <=4000" => Ok(Self::Gt3200Le4000),
            ">4000-5000" | ">4000 and <=5000" => Ok(Self::Gt4000Le5000),
            ">5000-6300" | ">5000 and <=6300" => Ok(Self::Gt5000Le6300),
            ">6300-8000" | ">6300 and <=8000" => Ok(Self::Gt6300Le8000),
            ">8000-10000" | ">8000 and <=10000" => Ok(Self::Gt8000Le10000),
            ">10000-12500" | ">10000 and <=12500" => Ok(Self::Gt10000Le12500),
            _ => Err(format!("unknown voltage range '{s}'")),
        }
    }
}

impl fmt::Display for VoltageRange {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}", self.as_str())
    }
}

// ---------------------------------------------------------------------------
// Table shapes
// ---------------------------------------------------------------------------

/// One row of a creepage table: a voltage bracket and the seven columns
/// `[PD1, PD2-I, PD2-II, PD2-IIIa/IIIb, PD3-I, PD3-II, PD3-IIIa/IIIb]`
/// (the printed column order of Table 17 and Table 18).
#[derive(Debug, Clone)]
pub struct CreepageTableRow {
    pub range: VoltageRange,
    pub cells: [SafetyValue; 7],
}

/// The column index for a (pollution degree, material group) pair.
pub const fn column_index(pd: PollutionDegree, group: MaterialGroup) -> usize {
    match (pd, group) {
        (PollutionDegree::PD1, _) => 0,
        (PollutionDegree::PD2, MaterialGroup::I) => 1,
        (PollutionDegree::PD2, MaterialGroup::II) => 2,
        (PollutionDegree::PD2, MaterialGroup::IIIaOrIIIb) => 3,
        (PollutionDegree::PD3, MaterialGroup::I) => 4,
        (PollutionDegree::PD3, MaterialGroup::II) => 5,
        (PollutionDegree::PD3, MaterialGroup::IIIaOrIIIb) => 6,
    }
}

/// Look up a cell in a creepage table by (voltage bracket, PD, material
/// group). Returns `None` only when the bracket is not present in the table.
pub fn creepage_lookup(
    table: &[CreepageTableRow],
    pd: PollutionDegree,
    group: MaterialGroup,
    range: VoltageRange,
) -> Option<&SafetyValue> {
    let row = table.iter().find(|row| row.range == range)?;
    Some(&row.cells[column_index(pd, group)])
}

/// Look up a basic-insulation creepage cell in recovered **Table 17**.
pub fn table_17_lookup(
    pd: PollutionDegree,
    group: MaterialGroup,
    range: VoltageRange,
) -> Option<&'static SafetyValue> {
    creepage_lookup(&TABLE_17, pd, group, range)
}

/// Look up a functional-insulation creepage cell in recovered **Table 18**.
pub fn table_18_lookup(
    pd: PollutionDegree,
    group: MaterialGroup,
    range: VoltageRange,
) -> Option<&'static SafetyValue> {
    creepage_lookup(&TABLE_18, pd, group, range)
}

// ---------------------------------------------------------------------------
// Table 17 — Minimum Creepage Distances for BASIC insulation (CITED-PRIMARY)
// ---------------------------------------------------------------------------
// Source: DOC_CREEPAGE_BRAINSTORM §3.3 (IS 302-1:2008 = IEC 60335-1, OCR'd,
// cell-for-cell cross-checked against Broadcom's IEC 60664-1 reproduction).
// Columns: PD1, then PD2 and PD3 each split by material group I / II /
// IIIa-IIIb (the standard merges IIIa and IIIb into one column).
// Clause 29.2.1: "Creepage distances of basic insulation shall not be less
// than those specified in Table 17."
// Row numbering (i..vii) follows the evidence docs: row iv = >250-400 V.

macro_rules! t17 {
    ($value_mm:expr, $row:expr) => {
        SafetyValue {
            value_mm: $value_mm,
            standard: Standard::IEC60335_1,
            provenance: Provenance::RecoveredPrimary {
                doc: DOC_CREEPAGE_BRAINSTORM,
                table: "Table 17",
                row: $row,
                clause: "29.2.1",
            },
        }
    };
}

/// Recovered Table 17, rows i–vii (working voltage <=1 000 V). Rows beyond
/// 1 000 V are not transcribed in the brainstorm doc; the verification doc
/// (§3) establishes they continue identically to Table 18's rows, which
/// ARE transcribed here (see `TABLE_18`).
pub const TABLE_17: [CreepageTableRow; 7] = [
    CreepageTableRow {
        range: VoltageRange::UpTo50,
        cells: [
            t17!(0.2, "row i (<=50 V), PD1"),
            t17!(0.6, "row i (<=50 V), PD2, group I"),
            t17!(0.9, "row i (<=50 V), PD2, group II"),
            t17!(1.2, "row i (<=50 V), PD2, group IIIa/IIIb"),
            t17!(1.5, "row i (<=50 V), PD3, group I"),
            t17!(1.7, "row i (<=50 V), PD3, group II"),
            t17!(1.9, "row i (<=50 V), PD3, group IIIa/IIIb"),
        ],
    },
    CreepageTableRow {
        range: VoltageRange::Gt50Le125,
        cells: [
            t17!(0.3, "row ii (>50-125 V), PD1"),
            t17!(0.8, "row ii (>50-125 V), PD2, group I"),
            t17!(1.1, "row ii (>50-125 V), PD2, group II"),
            t17!(1.5, "row ii (>50-125 V), PD2, group IIIa/IIIb"),
            t17!(1.9, "row ii (>50-125 V), PD3, group I"),
            t17!(2.1, "row ii (>50-125 V), PD3, group II"),
            t17!(2.4, "row ii (>50-125 V), PD3, group IIIa/IIIb"),
        ],
    },
    CreepageTableRow {
        range: VoltageRange::Gt125Le250,
        cells: [
            t17!(0.6, "row iii (>125-250 V), PD1"),
            t17!(1.3, "row iii (>125-250 V), PD2, group I"),
            t17!(1.8, "row iii (>125-250 V), PD2, group II"),
            t17!(2.5, "row iii (>125-250 V), PD2, group IIIa/IIIb"),
            t17!(3.2, "row iii (>125-250 V), PD3, group I"),
            t17!(3.6, "row iii (>125-250 V), PD3, group II"),
            t17!(4.0, "row iii (>125-250 V), PD3, group IIIa/IIIb"),
        ],
    },
    CreepageTableRow {
        range: VoltageRange::Gt250Le400,
        cells: [
            t17!(1.0, "row iv (>250-400 V), PD1"),
            t17!(2.0, "row iv (>250-400 V), PD2, group I"),
            t17!(2.8, "row iv (>250-400 V), PD2, group II"),
            t17!(4.0, "row iv (>250-400 V), PD2, group IIIa/IIIb"),
            t17!(5.0, "row iv (>250-400 V), PD3, group I"),
            t17!(5.6, "row iv (>250-400 V), PD3, group II"),
            t17!(6.3, "row iv (>250-400 V), PD3, group IIIa/IIIb"),
        ],
    },
    CreepageTableRow {
        range: VoltageRange::Gt400Le500,
        cells: [
            t17!(1.3, "row v (>400-500 V), PD1"),
            t17!(2.5, "row v (>400-500 V), PD2, group I"),
            t17!(3.6, "row v (>400-500 V), PD2, group II"),
            t17!(5.0, "row v (>400-500 V), PD2, group IIIa/IIIb"),
            t17!(6.3, "row v (>400-500 V), PD3, group I"),
            t17!(7.1, "row v (>400-500 V), PD3, group II"),
            t17!(8.0, "row v (>400-500 V), PD3, group IIIa/IIIb"),
        ],
    },
    CreepageTableRow {
        range: VoltageRange::Gt500Le800,
        cells: [
            t17!(1.8, "row vi (>500-800 V), PD1"),
            t17!(3.2, "row vi (>500-800 V), PD2, group I"),
            t17!(4.5, "row vi (>500-800 V), PD2, group II"),
            t17!(6.3, "row vi (>500-800 V), PD2, group IIIa/IIIb"),
            t17!(8.0, "row vi (>500-800 V), PD3, group I"),
            t17!(9.0, "row vi (>500-800 V), PD3, group II"),
            t17!(10.0, "row vi (>500-800 V), PD3, group IIIa/IIIb"),
        ],
    },
    CreepageTableRow {
        range: VoltageRange::Gt800Le1000,
        cells: [
            t17!(2.4, "row vii (>800-1000 V), PD1"),
            t17!(4.0, "row vii (>800-1000 V), PD2, group I"),
            t17!(5.6, "row vii (>800-1000 V), PD2, group II"),
            t17!(8.0, "row vii (>800-1000 V), PD2, group IIIa/IIIb"),
            t17!(10.0, "row vii (>800-1000 V), PD3, group I"),
            t17!(11.0, "row vii (>800-1000 V), PD3, group II"),
            t17!(12.5, "row vii (>800-1000 V), PD3, group IIIa/IIIb"),
        ],
    },
];

// ---------------------------------------------------------------------------
// Table 18 — Minimum Creepage Distances for FUNCTIONAL insulation
// ---------------------------------------------------------------------------
// Source: DOC_HV_HV_CREEPAGE §3.1 (CITED-PRIMARY, same IS 302-1:2008
// artifact). Same column layout as Table 17. Clause 29.2.4: "Creepage
// distances of functional insulation shall be not less than those specified
// in Table 18." The 2026-08-15 verification doc (§3) establishes that
// Table 17 continues past 1 000 V identical to this table, so the rows
// below beyond `Gt800Le1000` are also the Table 17 continuation rows.

macro_rules! t18 {
    ($value_mm:expr, $row:expr) => {
        SafetyValue {
            value_mm: $value_mm,
            standard: Standard::IEC60335_1,
            provenance: Provenance::RecoveredPrimary {
                doc: DOC_HV_HV_CREEPAGE,
                table: "Table 18",
                row: $row,
                clause: "29.2.4",
            },
        }
    };
}

/// Recovered Table 18, all 18 transcribed rows.
pub const TABLE_18: [CreepageTableRow; 18] = [
    CreepageTableRow {
        range: VoltageRange::UpTo50,
        cells: [
            t18!(0.2, "row (<=50 V), PD1"),
            t18!(0.6, "row (<=50 V), PD2, group I"),
            t18!(0.8, "row (<=50 V), PD2, group II"),
            t18!(1.1, "row (<=50 V), PD2, group IIIa/IIIb"),
            t18!(1.4, "row (<=50 V), PD3, group I"),
            t18!(1.6, "row (<=50 V), PD3, group II"),
            t18!(1.8, "row (<=50 V), PD3, group IIIa/IIIb"),
        ],
    },
    CreepageTableRow {
        range: VoltageRange::Gt50Le125,
        cells: [
            t18!(0.3, "row (>50-125 V), PD1"),
            t18!(0.7, "row (>50-125 V), PD2, group I"),
            t18!(1.0, "row (>50-125 V), PD2, group II"),
            t18!(1.4, "row (>50-125 V), PD2, group IIIa/IIIb"),
            t18!(1.8, "row (>50-125 V), PD3, group I"),
            t18!(2.0, "row (>50-125 V), PD3, group II"),
            t18!(2.2, "row (>50-125 V), PD3, group IIIa/IIIb"),
        ],
    },
    CreepageTableRow {
        range: VoltageRange::Gt125Le250,
        cells: [
            t18!(0.4, "row (>125-250 V), PD1"),
            t18!(1.0, "row (>125-250 V), PD2, group I"),
            t18!(1.4, "row (>125-250 V), PD2, group II"),
            t18!(2.0, "row (>125-250 V), PD2, group IIIa/IIIb"),
            t18!(2.5, "row (>125-250 V), PD3, group I"),
            t18!(2.8, "row (>125-250 V), PD3, group II"),
            t18!(3.2, "row (>125-250 V), PD3, group IIIa/IIIb"),
        ],
    },
    CreepageTableRow {
        range: VoltageRange::Gt250Le400,
        cells: [
            t18!(0.8, "row (>250-400 V), PD1"),
            t18!(1.6, "row (>250-400 V), PD2, group I"),
            t18!(2.2, "row (>250-400 V), PD2, group II"),
            t18!(3.2, "row (>250-400 V), PD2, group IIIa/IIIb"),
            t18!(4.0, "row (>250-400 V), PD3, group I"),
            t18!(4.5, "row (>250-400 V), PD3, group II"),
            t18!(5.0, "row (>250-400 V), PD3, group IIIa/IIIb"),
        ],
    },
    CreepageTableRow {
        range: VoltageRange::Gt400Le500,
        cells: [
            t18!(1.0, "row (>400-500 V), PD1"),
            t18!(2.0, "row (>400-500 V), PD2, group I"),
            t18!(2.8, "row (>400-500 V), PD2, group II"),
            t18!(4.0, "row (>400-500 V), PD2, group IIIa/IIIb"),
            t18!(5.0, "row (>400-500 V), PD3, group I"),
            t18!(5.6, "row (>400-500 V), PD3, group II"),
            t18!(6.3, "row (>400-500 V), PD3, group IIIa/IIIb"),
        ],
    },
    CreepageTableRow {
        range: VoltageRange::Gt500Le800,
        cells: [
            t18!(1.8, "row (>500-800 V), PD1"),
            t18!(3.2, "row (>500-800 V), PD2, group I"),
            t18!(4.5, "row (>500-800 V), PD2, group II"),
            t18!(6.3, "row (>500-800 V), PD2, group IIIa/IIIb"),
            t18!(8.0, "row (>500-800 V), PD3, group I"),
            t18!(9.0, "row (>500-800 V), PD3, group II"),
            t18!(10.0, "row (>500-800 V), PD3, group IIIa/IIIb"),
        ],
    },
    CreepageTableRow {
        range: VoltageRange::Gt800Le1000,
        cells: [
            t18!(2.4, "row (>800-1000 V), PD1"),
            t18!(4.0, "row (>800-1000 V), PD2, group I"),
            t18!(5.6, "row (>800-1000 V), PD2, group II"),
            t18!(8.0, "row (>800-1000 V), PD2, group IIIa/IIIb"),
            t18!(10.0, "row (>800-1000 V), PD3, group I"),
            t18!(11.0, "row (>800-1000 V), PD3, group II"),
            t18!(12.5, "row (>800-1000 V), PD3, group IIIa/IIIb"),
        ],
    },
    CreepageTableRow {
        range: VoltageRange::Gt1000Le1250,
        cells: [
            t18!(3.2, "row (>1000-1250 V), PD1"),
            t18!(5.0, "row (>1000-1250 V), PD2, group I"),
            t18!(7.1, "row (>1000-1250 V), PD2, group II"),
            t18!(10.0, "row (>1000-1250 V), PD2, group IIIa/IIIb"),
            t18!(12.5, "row (>1000-1250 V), PD3, group I"),
            t18!(14.0, "row (>1000-1250 V), PD3, group II"),
            t18!(16.0, "row (>1000-1250 V), PD3, group IIIa/IIIb"),
        ],
    },
    CreepageTableRow {
        range: VoltageRange::Gt1250Le1600,
        cells: [
            t18!(4.2, "row (>1250-1600 V), PD1"),
            t18!(6.3, "row (>1250-1600 V), PD2, group I"),
            t18!(9.0, "row (>1250-1600 V), PD2, group II"),
            t18!(12.5, "row (>1250-1600 V), PD2, group IIIa/IIIb"),
            t18!(16.0, "row (>1250-1600 V), PD3, group I"),
            t18!(18.0, "row (>1250-1600 V), PD3, group II"),
            t18!(20.0, "row (>1250-1600 V), PD3, group IIIa/IIIb"),
        ],
    },
    CreepageTableRow {
        range: VoltageRange::Gt1600Le2000,
        cells: [
            t18!(5.6, "row (>1600-2000 V), PD1"),
            t18!(8.0, "row (>1600-2000 V), PD2, group I"),
            t18!(11.0, "row (>1600-2000 V), PD2, group II"),
            t18!(16.0, "row (>1600-2000 V), PD2, group IIIa/IIIb"),
            t18!(20.0, "row (>1600-2000 V), PD3, group I"),
            t18!(22.0, "row (>1600-2000 V), PD3, group II"),
            t18!(25.0, "row (>1600-2000 V), PD3, group IIIa/IIIb"),
        ],
    },
    CreepageTableRow {
        range: VoltageRange::Gt2000Le2500,
        cells: [
            t18!(7.5, "row (>2000-2500 V), PD1"),
            t18!(10.0, "row (>2000-2500 V), PD2, group I"),
            t18!(14.0, "row (>2000-2500 V), PD2, group II"),
            t18!(20.0, "row (>2000-2500 V), PD2, group IIIa/IIIb"),
            t18!(25.0, "row (>2000-2500 V), PD3, group I"),
            t18!(28.0, "row (>2000-2500 V), PD3, group II"),
            t18!(32.0, "row (>2000-2500 V), PD3, group IIIa/IIIb"),
        ],
    },
    CreepageTableRow {
        range: VoltageRange::Gt2500Le3200,
        cells: [
            t18!(10.0, "row (>2500-3200 V), PD1"),
            t18!(12.5, "row (>2500-3200 V), PD2, group I"),
            t18!(18.0, "row (>2500-3200 V), PD2, group II"),
            t18!(25.0, "row (>2500-3200 V), PD2, group IIIa/IIIb"),
            t18!(32.0, "row (>2500-3200 V), PD3, group I"),
            t18!(36.0, "row (>2500-3200 V), PD3, group II"),
            t18!(40.0, "row (>2500-3200 V), PD3, group IIIa/IIIb"),
        ],
    },
    CreepageTableRow {
        range: VoltageRange::Gt3200Le4000,
        cells: [
            t18!(12.5, "row (>3200-4000 V), PD1"),
            t18!(16.0, "row (>3200-4000 V), PD2, group I"),
            t18!(22.0, "row (>3200-4000 V), PD2, group II"),
            t18!(32.0, "row (>3200-4000 V), PD2, group IIIa/IIIb"),
            t18!(40.0, "row (>3200-4000 V), PD3, group I"),
            t18!(45.0, "row (>3200-4000 V), PD3, group II"),
            t18!(50.0, "row (>3200-4000 V), PD3, group IIIa/IIIb"),
        ],
    },
    CreepageTableRow {
        range: VoltageRange::Gt4000Le5000,
        cells: [
            t18!(16.0, "row (>4000-5000 V), PD1"),
            t18!(20.0, "row (>4000-5000 V), PD2, group I"),
            t18!(28.0, "row (>4000-5000 V), PD2, group II"),
            t18!(40.0, "row (>4000-5000 V), PD2, group IIIa/IIIb"),
            t18!(50.0, "row (>4000-5000 V), PD3, group I"),
            t18!(56.0, "row (>4000-5000 V), PD3, group II"),
            t18!(63.0, "row (>4000-5000 V), PD3, group IIIa/IIIb"),
        ],
    },
    CreepageTableRow {
        range: VoltageRange::Gt5000Le6300,
        cells: [
            t18!(20.0, "row (>5000-6300 V), PD1"),
            t18!(25.0, "row (>5000-6300 V), PD2, group I"),
            t18!(36.0, "row (>5000-6300 V), PD2, group II"),
            t18!(50.0, "row (>5000-6300 V), PD2, group IIIa/IIIb"),
            t18!(63.0, "row (>5000-6300 V), PD3, group I"),
            t18!(71.0, "row (>5000-6300 V), PD3, group II"),
            t18!(80.0, "row (>5000-6300 V), PD3, group IIIa/IIIb"),
        ],
    },
    CreepageTableRow {
        range: VoltageRange::Gt6300Le8000,
        cells: [
            t18!(25.0, "row (>6300-8000 V), PD1"),
            t18!(32.0, "row (>6300-8000 V), PD2, group I"),
            t18!(45.0, "row (>6300-8000 V), PD2, group II"),
            t18!(63.0, "row (>6300-8000 V), PD2, group IIIa/IIIb"),
            t18!(80.0, "row (>6300-8000 V), PD3, group I"),
            t18!(90.0, "row (>6300-8000 V), PD3, group II"),
            t18!(100.0, "row (>6300-8000 V), PD3, group IIIa/IIIb"),
        ],
    },
    CreepageTableRow {
        range: VoltageRange::Gt8000Le10000,
        cells: [
            t18!(32.0, "row (>8000-10000 V), PD1"),
            t18!(40.0, "row (>8000-10000 V), PD2, group I"),
            t18!(56.0, "row (>8000-10000 V), PD2, group II"),
            t18!(80.0, "row (>8000-10000 V), PD2, group IIIa/IIIb"),
            t18!(100.0, "row (>8000-10000 V), PD3, group I"),
            t18!(110.0, "row (>8000-10000 V), PD3, group II"),
            t18!(125.0, "row (>8000-10000 V), PD3, group IIIa/IIIb"),
        ],
    },
    CreepageTableRow {
        range: VoltageRange::Gt10000Le12500,
        cells: [
            t18!(40.0, "row (>10000-12500 V), PD1"),
            t18!(50.0, "row (>10000-12500 V), PD2, group I"),
            t18!(71.0, "row (>10000-12500 V), PD2, group II"),
            t18!(100.0, "row (>10000-12500 V), PD2, group IIIa/IIIb"),
            t18!(125.0, "row (>10000-12500 V), PD3, group I"),
            t18!(140.0, "row (>10000-12500 V), PD3, group II"),
            t18!(160.0, "row (>10000-12500 V), PD3, group IIIa/IIIb"),
        ],
    },
];

// ---------------------------------------------------------------------------
// Table 16 — Minimum Clearances (CITED-PRIMARY)
// ---------------------------------------------------------------------------
// Source: DOC_CREEPAGE_BRAINSTORM §3.2. Keyed to rated impulse voltage.
// Clause 29.1.3: reinforced clearances use the next higher impulse-voltage
// step of Table 16. Clause 29.1.5: intermediate values may be determined by
// interpolation. Footnote at the 1 500 V row: "This value is increased to
// 0.8 mm for pollution degree 3".

macro_rules! t16 {
    ($value_mm:expr, $row:expr) => {
        SafetyValue {
            value_mm: $value_mm,
            standard: Standard::IEC60335_1,
            provenance: Provenance::RecoveredPrimary {
                doc: DOC_CREEPAGE_BRAINSTORM,
                table: "Table 16",
                row: $row,
                clause: "29.1.3",
            },
        }
    };
}

/// One row of the recovered clearance table.
#[derive(Debug, Clone)]
pub struct ClearanceRow {
    /// Rated impulse voltage (V) keying the row.
    pub impulse_voltage_v: u32,
    pub value: SafetyValue,
}

/// Recovered Table 16, all nine rows. The value set is
/// {0.5, 1.5, 3.0, 5.5, 8.0, 11.0} — the arithmetic proof that the repo's
/// clearance figures (4.0, 6.4, 6.0, 6.5) are not Table 16 values.
pub const TABLE_16: [ClearanceRow; 9] = [
    ClearanceRow { impulse_voltage_v: 330, value: t16!(0.5, "row (330 V rated impulse voltage)") },
    ClearanceRow { impulse_voltage_v: 500, value: t16!(0.5, "row (500 V rated impulse voltage)") },
    ClearanceRow { impulse_voltage_v: 800, value: t16!(0.5, "row (800 V rated impulse voltage)") },
    ClearanceRow { impulse_voltage_v: 1_500, value: t16!(0.5, "row (1 500 V rated impulse voltage)") },
    ClearanceRow { impulse_voltage_v: 2_500, value: t16!(1.5, "row (2 500 V rated impulse voltage)") },
    ClearanceRow { impulse_voltage_v: 4_000, value: t16!(3.0, "row (4 000 V rated impulse voltage)") },
    ClearanceRow { impulse_voltage_v: 6_000, value: t16!(5.5, "row (6 000 V rated impulse voltage)") },
    ClearanceRow { impulse_voltage_v: 8_000, value: t16!(8.0, "row (8 000 V rated impulse voltage)") },
    ClearanceRow { impulse_voltage_v: 10_000, value: t16!(11.0, "row (10 000 V rated impulse voltage)") },
];

/// The Table 16 footnote at the 1 500 V row: the clearance is increased to
/// 0.8 mm for pollution degree 3.
pub const TABLE_16_1500V_PD3_NOTE: SafetyValue = t16!(
    0.8,
    "row (1 500 V rated impulse voltage), footnote: increased to 0.8 mm for pollution degree 3"
);

/// Look up a basic-insulation clearance cell in recovered **Table 16** by
/// rated impulse voltage. Returns `None` for impulse voltages not in the
/// table (cl. 29.1.5 permits interpolation for intermediate values).
pub fn table_16_lookup(impulse_voltage_v: u32) -> Option<&'static SafetyValue> {
    TABLE_16
        .iter()
        .find(|row| row.impulse_voltage_v == impulse_voltage_v)
        .map(|row| &row.value)
}

// ---------------------------------------------------------------------------
// Derived values (clause 29.2.3 — reinforced = 2x Table 17 basic)
// ---------------------------------------------------------------------------

/// Clause 29.2.3: "Creepage distances of reinforced insulation shall be at
/// least double those specified for basic insulation in Table 17."
pub const CLAUSE_29_2_3: &str = "29.2.3";

/// Derive the reinforced creepage value from a Table 17 basic-insulation
/// cell by doubling it (cl. 29.2.3). The `from` cell is boxed into the
/// provenance so the derivation chain is inspectable.
pub fn creepage_reinforced(basic: &SafetyValue) -> SafetyValue {
    SafetyValue {
        value_mm: basic.value_mm() * 2.0,
        standard: basic.standard,
        provenance: Provenance::Derived {
            from: Box::new(basic.clone()),
            formula: "x2 (clause 29.2.3: reinforced = at least double Table 17 basic)",
            clause: CLAUSE_29_2_3,
        },
    }
}

/// Fetch a Table 17 cell, panicking only if the const table above is
/// internally inconsistent (a programming error, not a data condition).
fn t17_cell(pd: PollutionDegree, group: MaterialGroup, range: VoltageRange) -> SafetyValue {
    match table_17_lookup(pd, group, range) {
        Some(v) => v.clone(),
        None => panic!(
            "internal error: Table 17 const table missing cell for ({pd}, {group}, {range})"
        ),
    }
}

/// 8.0 mm — reinforced creepage, <=400 V barrier, PD2, material group
/// IIIa/IIIb (generic FR-4). Table 17 row iv (4.0) x 2 per cl. 29.2.3.
/// Matches `temper_placer/core/isolation_constants.py`'s
/// `MIN_BARRIER_WIDTH_MM = 8.0` and REQ-ELEC-04's own creepage table.
pub fn reinforced_creepage_400v_pd2() -> SafetyValue {
    let basic = t17_cell(PollutionDegree::PD2, MaterialGroup::IIIaOrIIIb, VoltageRange::Gt250Le400);
    SafetyValue {
        value_mm: basic.value_mm() * 2.0,
        standard: basic.standard,
        provenance: Provenance::Derived {
            from: Box::new(basic.clone()),
            formula: "4.0 x 2 = 8.0 (clause 29.2.3: reinforced = at least double Table 17 basic)",
            clause: CLAUSE_29_2_3,
        },
    }
}

/// 12.6 mm — reinforced creepage, <=400 V barrier, PD3, material group
/// IIIa/IIIb. Table 17 row iv (6.3) x 2 per cl. 29.2.3. This is the
/// PD3-as-built figure (handoff §7.C: PD3 governs the as-built board).
pub fn reinforced_creepage_400v_pd3() -> SafetyValue {
    let basic = t17_cell(PollutionDegree::PD3, MaterialGroup::IIIaOrIIIb, VoltageRange::Gt250Le400);
    SafetyValue {
        value_mm: basic.value_mm() * 2.0,
        standard: basic.standard,
        provenance: Provenance::Derived {
            from: Box::new(basic.clone()),
            formula: "6.3 x 2 = 12.6 (clause 29.2.3: reinforced = at least double Table 17 basic)",
            clause: CLAUSE_29_2_3,
        },
    }
}

/// 3.0 mm — reinforced creepage, 120 V mains, PD2, group IIIa/IIIb.
/// Table 17 row ii (1.5) x 2 per cl. 29.2.3.
pub fn reinforced_creepage_120v_pd2() -> SafetyValue {
    let basic = t17_cell(PollutionDegree::PD2, MaterialGroup::IIIaOrIIIb, VoltageRange::Gt50Le125);
    SafetyValue {
        value_mm: basic.value_mm() * 2.0,
        standard: basic.standard,
        provenance: Provenance::Derived {
            from: Box::new(basic.clone()),
            formula: "1.5 x 2 = 3.0 (clause 29.2.3: reinforced = at least double Table 17 basic)",
            clause: CLAUSE_29_2_3,
        },
    }
}

/// 4.8 mm — reinforced creepage, 120 V mains, PD3, group IIIa/IIIb.
/// Table 17 row ii (2.4) x 2 per cl. 29.2.3.
pub fn reinforced_creepage_120v_pd3() -> SafetyValue {
    let basic = t17_cell(PollutionDegree::PD3, MaterialGroup::IIIaOrIIIb, VoltageRange::Gt50Le125);
    SafetyValue {
        value_mm: basic.value_mm() * 2.0,
        standard: basic.standard,
        provenance: Provenance::Derived {
            from: Box::new(basic.clone()),
            formula: "2.4 x 2 = 4.8 (clause 29.2.3: reinforced = at least double Table 17 basic)",
            clause: CLAUSE_29_2_3,
        },
    }
}

/// 12.6 mm — reinforced creepage, 570.5 V resonant-tank band (>500-800 V),
/// PD2, group IIIa/IIIb. Table 17 row vi (6.3) x 2 per cl. 29.2.3.
pub fn reinforced_creepage_tank_pd2() -> SafetyValue {
    let basic = t17_cell(PollutionDegree::PD2, MaterialGroup::IIIaOrIIIb, VoltageRange::Gt500Le800);
    SafetyValue {
        value_mm: basic.value_mm() * 2.0,
        standard: basic.standard,
        provenance: Provenance::Derived {
            from: Box::new(basic.clone()),
            formula: "6.3 x 2 = 12.6 (clause 29.2.3: reinforced = at least double Table 17 basic)",
            clause: CLAUSE_29_2_3,
        },
    }
}

/// 20.0 mm — reinforced creepage, 570.5 V resonant-tank band (>500-800 V),
/// PD3, group IIIa/IIIb. Table 17 row vi (10.0) x 2 per cl. 29.2.3.
pub fn reinforced_creepage_tank_pd3() -> SafetyValue {
    let basic = t17_cell(PollutionDegree::PD3, MaterialGroup::IIIaOrIIIb, VoltageRange::Gt500Le800);
    SafetyValue {
        value_mm: basic.value_mm() * 2.0,
        standard: basic.standard,
        provenance: Provenance::Derived {
            from: Box::new(basic.clone()),
            formula: "10.0 x 2 = 20.0 (clause 29.2.3: reinforced = at least double Table 17 basic)",
            clause: CLAUSE_29_2_3,
        },
    }
}

// ---------------------------------------------------------------------------
// Legacy fabricated values (migration labels — NOT for production use)
// ---------------------------------------------------------------------------

/// The legacy `HIGH_VOLTAGE => 14.0` creepage base as a `Fabricated` label.
///
/// Introduced 2026-01-07 in `temper_placer/core/net_types.py` (commit
/// `418fab757`) with a bare "IEC 60335-1 Table 17 (basic insulation,
/// material group II)" comment and no row, clause, or derivation. The
/// recovered Table 17's maximum applicable value is 12.5 mm; the only
/// genuine 14.0 cells in the recovered tables require working voltage
/// above 1 000 V AND material group II — neither of which applies to this
/// board's HIGH_VOLTAGE nets (120-570.5 Vrms, generic FR-4 IIIa/IIIb).
/// See [`DOC_CREEPAGE_BASE_14_VERIFICATION`].
pub fn legacy_creepage_base_high_voltage_14_0() -> SafetyValue {
    SafetyValue {
        value_mm: 14.0,
        standard: Standard::IEC60335_1,
        provenance: Provenance::Fabricated {
            origin_commit: "418fab757",
            note: "introduced with a bare 'IEC 60335-1 Table 17 (basic insulation, material group II)' comment, no row/clause; recovered Table 17 max applicable value is 12.5; the only genuine 14.0 cells require >1 kV working voltage AND material group II (see docs/evidence/2026-08-15-creepage-base-14-verification.md)",
        },
    }
}

/// The full legacy `VoltageClass.get_creepage_mm` base table as
/// `Fabricated` labels, in declaration order
/// `[SELV, LOW_VOLTAGE, MAINS_120V, MAINS_240V, HIGH_VOLTAGE]`.
///
/// The verification doc (§4) shows the "material group II" comment is false
/// for two of five entries, two more are cells of the wrong table, and 14.0
/// matches no applicable cell at all; the `base x {0.8, 1.0, 1.4}` scaling
/// structure itself is not Table 17's structure (material group selects a
/// column, and column ratios vary by row).
pub fn legacy_creepage_table() -> [SafetyValue; 5] {
    [
        SafetyValue {
            value_mm: 0.5,
            standard: Standard::IEC60335_1,
            provenance: Provenance::Fabricated {
                origin_commit: "418fab757",
                note: "SELV base: matches a Table 16 CLEARANCE cell (0.5 mm at 330-1500 V rated impulse voltage), not any Table 17 creepage cell; the 'Table 17 group II' comment is false",
            },
        },
        SafetyValue {
            value_mm: 1.6,
            standard: Standard::IEC60335_1,
            provenance: Provenance::Fabricated {
                origin_commit: "418fab757",
                note: "LOW_VOLTAGE base: matches Table 18 FUNCTIONAL creepage cell (>250-400 V, PD2, group I = 1.6); claimed as Table 17 basic group II — false",
            },
        },
        SafetyValue {
            value_mm: 2.5,
            standard: Standard::IEC60335_1,
            provenance: Provenance::Fabricated {
                origin_commit: "418fab757",
                note: "MAINS_120V base: is a Table 17 row iii (>125-250 V) PD2 group IIIa/IIIb cell — a IIIa/IIIb value, not group II as the comment claims",
            },
        },
        SafetyValue {
            value_mm: 5.0,
            standard: Standard::IEC60335_1,
            provenance: Provenance::Fabricated {
                origin_commit: "418fab757",
                note: "MAINS_240V base: is a Table 17 row v (>400-500 V) PD2 group IIIa/IIIb cell — a IIIa/IIIb value, not group II as the comment claims",
            },
        },
        legacy_creepage_base_high_voltage_14_0(),
    ]
}

// ---------------------------------------------------------------------------
// REQ-SAFE-01 / placer requirement matrix — single-sourced 2026-08-17
// (placer constraint/clearance Rust-port stage 1;
// docs/evidence/2026-08-17-domain-clearance-netclass-rust-port-stages-1-2.md,
// spec docs/evidence/2026-08-17-placer-constraint-rust-port-spike.md).
// ---------------------------------------------------------------------------
//
// Before this change the same 6 (domain_a, domain_b, insulation) rows were
// hand-duplicated in two places: the Python `IEC60335_REQUIREMENTS` dict
// (`temper_placer/requirements/validators/clearance.py`) and this crate's
// sibling `temper-drc-rs::req_safe_01::MATRIX_ROWS` const, nominally kept in
// sync by `test_requirement_matrix_values_pinned` — a test named in
// comments in BOTH files that does not actually exist anywhere in the tree
// (grepped at port time: zero hits; `git grep` confirms). [`requirement_matrix`]
// below is now the one array: `req_safe_01::req_safe_01_requirement_matrix()`
// (the pyo3 accessor) and `domain_clearance.py::_matrix_rows()` both read
// from it, directly or through that accessor.
//
// Every value below is byte-identical to the pre-port
// `MATRIX_ROWS`/`IEC60335_REQUIREMENTS` (hard rule: never change a
// clearance/creepage value; this consolidation moves zero figures). Creepage
// cells reuse this module's own recovered Table 17 (basic cell, doubled per
// cl. 29.2.3 for the reinforced rows) / Table 18 (functional row i) cells —
// real, already-encoded `SafetyValue` provenance, not re-derived here.
// Clearance cells are carried forward **UNSOURCED**, exactly as the
// pre-port Python comment documented (not a Table 16 value — Table 16's
// value set is {0.5, 1.5, 3.0, 5.5, 8.0, 11.0} but is keyed by rated impulse
// voltage, not by the domain pairs here; see
// `docs/evidence/2026-07-28-creepage-determination-brainstorm.md` §4). This
// port does not manufacture a false `RecoveredPrimary`/`Derived` provenance
// for them (the "never invent or reconstruct a standards value" rule) —
// they stay plain `f64`, not `SafetyValue`, so the type itself signals "no
// standards chain attached" instead of asserting one that would be false.
// `design_value_mm` is an as-built target dimension that
// `req_safe_01_verify_iec60335` never reads (only clearance/creepage feed
// the validator); also carried forward as plain `f64` for the same reason.

/// One row of the placer's IEC 60335 domain-clearance/creepage requirement
/// matrix. See the module note above for why `clearance_mm`/
/// `design_value_mm` are plain `f64` while `creepage` is a full
/// [`SafetyValue`].
#[derive(Debug, Clone)]
pub struct RequirementRow {
    pub domain_a: &'static str,
    pub domain_b: &'static str,
    pub insulation: &'static str,
    /// UNSOURCED — not a Table 16 citation (see module note above).
    pub clearance_mm: f64,
    pub creepage: SafetyValue,
    /// As-built target; not a standards citation, not read by the validator.
    pub design_value_mm: f64,
}

/// The 6-row placer requirement matrix, single-sourced. Not `const` because
/// it reuses the existing non-const `t17_cell`/`table_18_lookup` accessors —
/// matches [`legacy_creepage_table`]'s existing plain-fn pattern in this
/// same file.
pub fn requirement_matrix() -> [RequirementRow; 6] {
    let basic_400v_pd3 =
        t17_cell(PollutionDegree::PD3, MaterialGroup::IIIaOrIIIb, VoltageRange::Gt250Le400);
    let reinforced_400v_pd3 = reinforced_creepage_400v_pd3();
    let functional_50v_pd3 = match table_18_lookup(
        PollutionDegree::PD3,
        MaterialGroup::IIIaOrIIIb,
        VoltageRange::UpTo50,
    ) {
        Some(v) => v.clone(),
        None => panic!(
            "internal error: Table 18 const table missing cell for (PD3, IIIa/IIIb, <=50V)"
        ),
    };

    [
        RequirementRow {
            domain_a: "MAINS",
            domain_b: "LV_CONTROL",
            insulation: "basic",
            clearance_mm: 3.0,
            creepage: basic_400v_pd3.clone(),
            design_value_mm: 8.3,
        },
        RequirementRow {
            domain_a: "MAINS",
            domain_b: "LV_CONTROL",
            insulation: "reinforced",
            clearance_mm: 6.0,
            creepage: reinforced_400v_pd3.clone(),
            design_value_mm: 14.6,
        },
        RequirementRow {
            domain_a: "DC_BUS",
            domain_b: "LV_CONTROL",
            insulation: "basic",
            clearance_mm: 3.0,
            creepage: basic_400v_pd3,
            design_value_mm: 8.3,
        },
        RequirementRow {
            domain_a: "DC_BUS",
            domain_b: "LV_CONTROL",
            insulation: "reinforced",
            clearance_mm: 6.0,
            creepage: reinforced_400v_pd3.clone(),
            design_value_mm: 14.6,
        },
        RequirementRow {
            domain_a: "MAINS",
            domain_b: "ISOLATED",
            insulation: "reinforced",
            clearance_mm: 6.0,
            creepage: reinforced_400v_pd3,
            design_value_mm: 14.6,
        },
        RequirementRow {
            domain_a: "LV_CONTROL",
            domain_b: "LV_CONTROL",
            insulation: "functional",
            clearance_mm: 0.5,
            creepage: functional_50v_pd3,
            design_value_mm: 2.0,
        },
    ]
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

    #[cfg_attr(test, test)]
    fn recovered_primary_constructs_and_reads_back() {
        let cell = t17_cell(PollutionDegree::PD2, MaterialGroup::IIIaOrIIIb, VoltageRange::Gt250Le400);
        assert_eq!(cell.value_mm(), 4.0);
        assert_eq!(cell.standard(), Standard::IEC60335_1);
        assert!(!cell.is_fabricated());
        assert!(!cell.is_unobtainable());
        match cell.provenance() {
            Provenance::RecoveredPrimary { doc, table, row, clause } => {
                assert_eq!(*doc, DOC_CREEPAGE_BRAINSTORM);
                assert_eq!(*table, "Table 17");
                assert_eq!(*row, "row iv (>250-400 V), PD2, group IIIa/IIIb");
                assert_eq!(*clause, "29.2.1");
            }
            other => panic!("expected RecoveredPrimary, got {other:?}"),
        }
        assert!(cell.provenance_debug().contains("RecoveredPrimary: Table 17"));
    }

    #[cfg_attr(test, test)]
    fn legacy_14_0_is_fabricated_with_origin_commit() {
        let legacy = legacy_creepage_base_high_voltage_14_0();
        assert_eq!(legacy.value_mm(), 14.0);
        assert!(legacy.is_fabricated());
        match legacy.provenance() {
            Provenance::Fabricated { origin_commit, .. } => {
                assert_eq!(*origin_commit, "418fab757");
            }
            other => panic!("expected Fabricated, got {other:?}"),
        }
        // The full legacy table carries five fabricated entries, the last
        // being the 14.0 base itself.
        let all = legacy_creepage_table();
        assert_eq!(all.len(), 5);
        assert!(all.iter().all(SafetyValue::is_fabricated));
        assert_eq!(all[4].value_mm(), 14.0);
    }

    #[cfg_attr(test, test)]
    fn correct_values_are_derived_not_fabricated() {
        let pd2 = reinforced_creepage_400v_pd2();
        assert_eq!(pd2.value_mm(), 8.0);
        assert!(!pd2.is_fabricated());
        match pd2.provenance() {
            Provenance::Derived { from, formula, clause } => {
                // The from-cell is the recovered Table 17 basic value.
                assert_eq!(from.value_mm(), 4.0);
                assert!(matches!(
                    from.provenance(),
                    Provenance::RecoveredPrimary { .. }
                ));
                assert!(formula.contains("8.0"));
                assert_eq!(*clause, CLAUSE_29_2_3);
            }
            other => panic!("expected Derived, got {other:?}"),
        }

        let pd3 = reinforced_creepage_400v_pd3();
        assert_eq!(pd3.value_mm(), 12.6);
        assert!(!pd3.is_fabricated());
        match pd3.provenance() {
            Provenance::Derived { from, .. } => assert_eq!(from.value_mm(), 6.3),
            other => panic!("expected Derived, got {other:?}"),
        }

        // Tank-band figures from the verification doc §5.
        assert_eq!(reinforced_creepage_tank_pd2().value_mm(), 12.6);
        assert_eq!(reinforced_creepage_tank_pd3().value_mm(), 20.0);
        assert_eq!(reinforced_creepage_120v_pd2().value_mm(), 3.0);
        assert_eq!(reinforced_creepage_120v_pd3().value_mm(), 4.8);
    }

    #[cfg_attr(test, test)]
    fn table_17_lookup_returns_recovered_cells() {
        // Spot cells cross-checked against the recovered table and the
        // verification doc §5.
        let pd2_iii = table_17_lookup(PollutionDegree::PD2, MaterialGroup::IIIaOrIIIb, VoltageRange::Gt250Le400).expect("row iv");
        assert_eq!(pd2_iii.value_mm(), 4.0);

        let pd3_iii = table_17_lookup(PollutionDegree::PD3, MaterialGroup::IIIaOrIIIb, VoltageRange::Gt250Le400).expect("row iv");
        assert_eq!(pd3_iii.value_mm(), 6.3);

        // Row v (>400-500 V) PD3 group IIIa/IIIb = 8.0 (verification doc §5
        // tank row also cites 10.0 at >500-800 PD3).
        assert_eq!(
            table_17_lookup(PollutionDegree::PD3, MaterialGroup::IIIaOrIIIb, VoltageRange::Gt400Le500)
                .expect("row v")
                .value_mm(),
            8.0
        );
        assert_eq!(
            table_17_lookup(PollutionDegree::PD3, MaterialGroup::IIIaOrIIIb, VoltageRange::Gt500Le800)
                .expect("row vi")
                .value_mm(),
            10.0
        );

        // PD1 uses the single merged column regardless of group.
        let pd1_i = table_17_lookup(PollutionDegree::PD1, MaterialGroup::I, VoltageRange::Gt250Le400).expect("row iv");
        let pd1_iii = table_17_lookup(PollutionDegree::PD1, MaterialGroup::IIIaOrIIIb, VoltageRange::Gt250Le400).expect("row iv");
        assert_eq!(pd1_i.value_mm(), 1.0);
        assert_eq!(pd1_iii.value_mm(), 1.0);

        // A bracket beyond the transcribed rows is a clean None.
        assert!(table_17_lookup(
            PollutionDegree::PD2,
            MaterialGroup::IIIaOrIIIb,
            VoltageRange::Gt1000Le1250
        )
        .is_none());
    }

    #[cfg_attr(test, test)]
    fn table_17_max_applicable_value_is_12_5() {
        // Verification doc §3: recovered Table 17 value set tops out at 12.5
        // for the transcribed rows.
        let max = TABLE_17
            .iter()
            .flat_map(|row| row.cells.iter())
            .map(SafetyValue::value_mm)
            .fold(f64::NEG_INFINITY, f64::max);
        assert_eq!(max, 12.5);
    }

    #[cfg_attr(test, test)]
    fn table_18_rows_agree_with_table_17_where_they_overlap() {
        // The verification doc (§3) establishes Table 17 continues past
        // 1 000 V identical to Table 18. The recovered overlap (>500-1000 V
        // rows) must agree cell-for-cell between the two tables.
        for range in [VoltageRange::Gt500Le800, VoltageRange::Gt800Le1000] {
            for pd in [PollutionDegree::PD1, PollutionDegree::PD2, PollutionDegree::PD3] {
                for group in [MaterialGroup::I, MaterialGroup::II, MaterialGroup::IIIaOrIIIb] {
                    let a = table_17_lookup(pd, group, range).expect("table 17 row");
                    let b = table_18_lookup(pd, group, range).expect("table 18 row");
                    assert_eq!(
                        a.value_mm(),
                        b.value_mm(),
                        "mismatch at {range:?} {pd} {group}"
                    );
                }
            }
        }
    }

    #[cfg_attr(test, test)]
    fn table_18_genuine_14_0_cells_require_high_voltage_and_group_ii() {
        // Verification doc §3: the only genuine 14.0 cells are
        // (>1000-1250 V, PD3, group II) and (>2000-2500 V, PD2, group II).
        assert_eq!(
            table_18_lookup(PollutionDegree::PD3, MaterialGroup::II, VoltageRange::Gt1000Le1250)
                .expect("cell")
                .value_mm(),
            14.0
        );
        assert_eq!(
            table_18_lookup(PollutionDegree::PD2, MaterialGroup::II, VoltageRange::Gt2000Le2500)
                .expect("cell")
                .value_mm(),
            14.0
        );
    }

    #[cfg_attr(test, test)]
    fn table_16_clearances_match_recovered_value_set() {
        // Handoff §3: Table 16's value set is {0.5, 1.5, 3.0, 5.5, 8.0, 11.0}.
        let values: Vec<f64> = TABLE_16.iter().map(|r| r.value.value_mm()).collect();
        assert_eq!(values, vec![0.5, 0.5, 0.5, 0.5, 1.5, 3.0, 5.5, 8.0, 11.0]);

        assert_eq!(table_16_lookup(1_500).expect("1500 V").value_mm(), 0.5);
        assert_eq!(table_16_lookup(2_500).expect("2500 V").value_mm(), 1.5);
        assert_eq!(table_16_lookup(10_000).expect("10000 V").value_mm(), 11.0);
        assert!(table_16_lookup(1_200).is_none());

        // The PD3 footnote at 1 500 V.
        assert_eq!(TABLE_16_1500V_PD3_NOTE.value_mm(), 0.8);
        assert!(matches!(
            TABLE_16_1500V_PD3_NOTE.provenance(),
            Provenance::RecoveredPrimary { .. }
        ));
    }

    #[cfg_attr(test, test)]
    fn unobtainable_values_are_nan_and_flagged() {
        let f = iec60664_4_frequency_dependent_creepage();
        assert!(f.is_unobtainable());
        assert!(f.value_mm().is_nan());
        assert!(f.provenance_debug().contains("Unobtainable"));

        let t9 = table_9_temperature_rise();
        assert!(t9.is_unobtainable());
        assert!(t9.value_mm().is_nan());
        // The marker documents the handoff's "Table 9" as temperature rises,
        // not clearance.
        assert!(t9.provenance_debug().contains("temperature rises"));
    }

    #[cfg_attr(test, test)]
    fn every_table_cell_carries_recovered_primary_provenance() {
        for row in TABLE_17.iter().chain(TABLE_18.iter()) {
            for cell in &row.cells {
                assert!(matches!(
                    cell.provenance(),
                    Provenance::RecoveredPrimary { .. }
                ));
                assert!(!cell.is_fabricated());
                assert!(!cell.is_unobtainable());
                assert!(cell.value_mm().is_finite() && cell.value_mm() > 0.0);
            }
        }
    }

    #[cfg_attr(test, test)]
    fn table_17_and_18_lookup_find_every_defined_bracket() {
        for range in TABLE_17.iter().map(|r| r.range) {
            assert!(table_17_lookup(PollutionDegree::PD2, MaterialGroup::IIIaOrIIIb, range).is_some());
        }
        for range in TABLE_18.iter().map(|r| r.range) {
            assert!(table_18_lookup(PollutionDegree::PD2, MaterialGroup::IIIaOrIIIb, range).is_some());
        }
    }

    #[cfg_attr(test, test)]
    fn voltage_range_parsing_round_trips() {
        for range in [
            VoltageRange::UpTo50,
            VoltageRange::Gt250Le400,
            VoltageRange::Gt10000Le12500,
        ] {
            assert_eq!(VoltageRange::from_str(range.as_str()), Ok(range));
        }
        // Long form accepted (evidence docs' phrasing).
        assert_eq!(
            VoltageRange::from_str(">250 and <=400"),
            Ok(VoltageRange::Gt250Le400)
        );
        assert!(VoltageRange::from_str("bogus").is_err());
    }

    #[cfg_attr(test, test)]
    fn material_group_parsing_merges_iiia_and_iiib() {
        assert_eq!(MaterialGroup::from_str("I"), Ok(MaterialGroup::I));
        assert_eq!(MaterialGroup::from_str("II"), Ok(MaterialGroup::II));
        assert_eq!(MaterialGroup::from_str("IIIa/IIIb"), Ok(MaterialGroup::IIIaOrIIIb));
        assert_eq!(MaterialGroup::from_str("IIIa"), Ok(MaterialGroup::IIIaOrIIIb));
        assert_eq!(MaterialGroup::from_str("IIIb"), Ok(MaterialGroup::IIIaOrIIIb));
        assert!(MaterialGroup::from_str("IV").is_err());
    }

    #[cfg_attr(test, test)]
    fn requirement_matrix_matches_pre_port_values_exactly() {
        // Pins the single-sourced matrix against the pre-port
        // MATRIX_ROWS/IEC60335_REQUIREMENTS values byte-for-byte (2026-08-17
        // placer constraint/clearance Rust-port stage 1). Any failure here
        // means a value moved -- stop and report, do not "fix" this test.
        let rows = requirement_matrix();
        let expected: [(&str, &str, &str, f64, f64, f64); 6] = [
            ("MAINS", "LV_CONTROL", "basic", 3.0, 6.3, 8.3),
            ("MAINS", "LV_CONTROL", "reinforced", 6.0, 12.6, 14.6),
            ("DC_BUS", "LV_CONTROL", "basic", 3.0, 6.3, 8.3),
            ("DC_BUS", "LV_CONTROL", "reinforced", 6.0, 12.6, 14.6),
            ("MAINS", "ISOLATED", "reinforced", 6.0, 12.6, 14.6),
            ("LV_CONTROL", "LV_CONTROL", "functional", 0.5, 1.8, 2.0),
        ];
        assert_eq!(rows.len(), expected.len());
        for (row, (da, db, ins, clr, crp, design)) in rows.iter().zip(expected.iter()) {
            assert_eq!(row.domain_a, *da);
            assert_eq!(row.domain_b, *db);
            assert_eq!(row.insulation, *ins);
            assert_eq!(row.clearance_mm, *clr);
            assert_eq!(row.creepage.value_mm(), *crp);
            assert_eq!(row.design_value_mm, *design);
            // Creepage carries real standards provenance, never fabricated
            // or unobtainable, for every row.
            assert!(!row.creepage.is_fabricated());
            assert!(!row.creepage.is_unobtainable());
        }
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("safety_value::tests::recovered_primary_constructs_and_reads_back", recovered_primary_constructs_and_reads_back),
        ("safety_value::tests::legacy_14_0_is_fabricated_with_origin_commit", legacy_14_0_is_fabricated_with_origin_commit),
        ("safety_value::tests::correct_values_are_derived_not_fabricated", correct_values_are_derived_not_fabricated),
        ("safety_value::tests::table_17_lookup_returns_recovered_cells", table_17_lookup_returns_recovered_cells),
        ("safety_value::tests::table_17_max_applicable_value_is_12_5", table_17_max_applicable_value_is_12_5),
        ("safety_value::tests::table_18_rows_agree_with_table_17_where_they_overlap", table_18_rows_agree_with_table_17_where_they_overlap),
        ("safety_value::tests::table_18_genuine_14_0_cells_require_high_voltage_and_group_ii", table_18_genuine_14_0_cells_require_high_voltage_and_group_ii),
        ("safety_value::tests::table_16_clearances_match_recovered_value_set", table_16_clearances_match_recovered_value_set),
        ("safety_value::tests::unobtainable_values_are_nan_and_flagged", unobtainable_values_are_nan_and_flagged),
        ("safety_value::tests::every_table_cell_carries_recovered_primary_provenance", every_table_cell_carries_recovered_primary_provenance),
        ("safety_value::tests::table_17_and_18_lookup_find_every_defined_bracket", table_17_and_18_lookup_find_every_defined_bracket),
        ("safety_value::tests::voltage_range_parsing_round_trips", voltage_range_parsing_round_trips),
        ("safety_value::tests::material_group_parsing_merges_iiia_and_iiib", material_group_parsing_merges_iiia_and_iiib),
        ("safety_value::tests::requirement_matrix_matches_pre_port_values_exactly", requirement_matrix_matches_pre_port_values_exactly),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}

// ---------------------------------------------------------------------------
// Python bindings (python feature only)
// ---------------------------------------------------------------------------

#[cfg(feature = "python")]
use pyo3::exceptions::PyValueError;
#[cfg(feature = "python")]
use pyo3::prelude::*;

/// Python-visible wrapper around [`SafetyValue`]. Immutable; constructed only
/// by the lookup functions below (or by tests). `skip_from_py_object`: the
/// class is never extracted from Python arguments (pyo3 0.29's opt-in
/// requirement).
#[cfg(feature = "python")]
#[pyclass(frozen, skip_from_py_object)]
#[derive(Clone, Debug)]
pub struct PySafetyValue {
    inner: SafetyValue,
}

#[cfg(feature = "python")]
#[pymethods]
impl PySafetyValue {
    /// The value in millimetres (`nan` when unobtainable).
    fn value_mm(&self) -> f64 {
        self.inner.value_mm()
    }

    /// The standard this value traces to, as a string, e.g. `"IEC60335_1"`.
    fn standard(&self) -> String {
        format!("{:?}", self.inner.standard())
    }

    /// Human-readable provenance description.
    fn provenance_debug(&self) -> String {
        self.inner.provenance_debug()
    }

    /// True when this is a known-fabricated legacy label.
    fn is_fabricated(&self) -> bool {
        self.inner.is_fabricated()
    }

    /// True when the value is explicitly unknown (paywalled standard,
    /// untranscribed table). `value_mm()` is `nan`.
    fn is_unobtainable(&self) -> bool {
        self.inner.is_unobtainable()
    }
}

#[cfg(feature = "python")]
fn to_py(value: &SafetyValue) -> PySafetyValue {
    PySafetyValue {
        inner: value.clone(),
    }
}

/// Look up a recovered creepage cell.
///
/// - `pd`: pollution degree, 1, 2 or 3
/// - `material_group`: `"I"`, `"II"`, `"IIIa/IIIb"` (also `"IIIa"`, `"IIIb"`
///   — the standard merges them into one column)
/// - `voltage_range`: e.g. `">250-400"` (also accepts `">250 and <=400"`)
/// - `table`: `"17"` (basic, cl. 29.2.1, default) or `"18"` (functional,
///   cl. 29.2.4)
///
/// Raises `ValueError` on an unknown key or a bracket the table does not
/// cover.
#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(signature = (pd, material_group, voltage_range, table="17"))]
fn creepage_table_lookup(
    pd: u8,
    material_group: &str,
    voltage_range: &str,
    table: &str,
) -> PyResult<PySafetyValue> {
    let pd = PollutionDegree::from_u8(pd)
        .ok_or_else(|| PyValueError::new_err(format!("pollution degree must be 1, 2 or 3; got {pd}")))?;
    let group = MaterialGroup::from_str(material_group)
        .map_err(|e| PyValueError::new_err(format!("{e}; expected 'I', 'II' or 'IIIa/IIIb'")))?;
    let range = VoltageRange::from_str(voltage_range).map_err(PyValueError::new_err)?;
    let cell = match table {
        "17" => table_17_lookup(pd, group, range),
        "18" => table_18_lookup(pd, group, range),
        other => {
            return Err(PyValueError::new_err(format!(
                "table must be '17' or '18'; got '{other}'"
            )))
        }
    };
    match cell {
        Some(v) => Ok(to_py(v)),
        None => Err(PyValueError::new_err(format!(
            "no Table {table} cell for PD{pd}, group {group}, voltage {range}"
        ))),
    }
}

/// Look up a recovered Table 16 clearance cell by rated impulse voltage (V).
/// Raises `ValueError` for impulse voltages not in the table (cl. 29.1.5
/// permits interpolation for intermediate values).
#[cfg(feature = "python")]
#[pyfunction]
fn clearance_table_lookup(impulse_voltage_v: u32) -> PyResult<PySafetyValue> {
    match table_16_lookup(impulse_voltage_v) {
        Some(v) => Ok(to_py(v)),
        None => Err(PyValueError::new_err(format!(
            "no Table 16 clearance row for rated impulse voltage {impulse_voltage_v} V; rows are 330, 500, 800, 1500, 2500, 4000, 6000, 8000, 10000"
        ))),
    }
}

/// Register the safety-value surface on the `temper_design_bundle_python`
/// module.
#[cfg(feature = "python")]
pub fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<PySafetyValue>()?;
    module.add_function(wrap_pyfunction!(creepage_table_lookup, module)?)?;
    module.add_function(wrap_pyfunction!(clearance_table_lookup, module)?)?;
    Ok(())
}
