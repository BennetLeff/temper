//! Typed assurance boundary for numerical PFC loss models.
//!
//! A numerical replay can be correct while its inputs are inapplicable to the
//! physical unit.  This module keeps those claims separate and fails closed
//! when a production adapter loses provenance, term identity, or its external
//! reference comparison.

use serde::Serialize;
use zapote_core::{CheckReport, Finding, Status};

pub const RULES: [&str; 3] = [
    "THERMAL.PFC.MODEL_NUMERICAL",
    "THERMAL.PFC.MODEL_APPLICABILITY",
    "QUALIFICATION.PFC.MODEL",
];
/// The authored decision point.  Other line/current values remain sensitivity
/// cases and cannot silently become the production decision input.
const NOMINAL_LINE_RMS_V: f64 = 120.0;
const NOMINAL_CURRENT_RMS_A: f64 = 15.0;

#[derive(Clone, Copy, Debug, Serialize, PartialEq, Eq, PartialOrd, Ord)]
pub enum Unit {
    Volt,
    Amp,
    Watt,
    Joule,
    Hertz,
    Second,
    Ohm,
    Coulomb,
    Henry,
    Celsius,
}

#[derive(Clone, Copy, Debug, Serialize, PartialEq, Eq)]
pub enum EvidenceKind {
    IndependentReference,
    Datasheet,
    Measured,
    Derived,
    Assumption,
}

#[derive(Clone, Debug, Serialize)]
pub struct EvidenceRef {
    pub source: String,
    pub sha256: Option<String>,
    pub kind: EvidenceKind,
    pub test_conditions: Vec<String>,
    pub applicability: String,
    pub stale: bool,
}

#[derive(Clone, Debug, Serialize)]
pub struct Quantity {
    pub value: f64,
    pub unit: Unit,
    pub source: String,
    pub evidence_kind: EvidenceKind,
    pub test_conditions: Vec<String>,
    pub applicability: String,
    pub unknowns: Vec<String>,
}

#[derive(Clone, Debug, Serialize)]
pub struct IndependentReference {
    pub evidence: EvidenceRef,
    pub reference: Quantity,
    pub observed: Quantity,
    pub tolerance: f64,
}

#[derive(Clone, Copy, Debug, Serialize, PartialEq, Eq, PartialOrd, Ord)]
pub enum TermClass {
    SwitchingOverlap,
    OutputCapacitance,
    Conduction,
    GateNetwork,
}

#[derive(Clone, Debug, Serialize)]
pub struct LossTerm {
    pub name: String,
    pub class: TermClass,
    pub value: Quantity,
    pub disjoint_key: String,
}

#[derive(Clone, Debug, Serialize)]
pub struct UnknownTerm {
    pub name: String,
    pub reason: String,
    pub may_change_outcome: bool,
}

#[derive(Clone, Debug, Serialize)]
pub struct AssuranceInput {
    pub source_provenance: EvidenceRef,
    pub nominal_line_rms: Quantity,
    pub nominal_current_rms: Quantity,
    pub gate_drive: Quantity,
    pub terms: Vec<LossTerm>,
    pub unknowns: Vec<UnknownTerm>,
    pub independent_reference: Option<IndependentReference>,
}

#[derive(Clone, Debug, Serialize)]
pub struct DimensionResult {
    pub status: Status,
    pub rationale: String,
    pub unknowns: Vec<String>,
}

#[derive(Clone, Debug, Serialize)]
pub struct ModelAssuranceReport {
    pub numerical_verification: DimensionResult,
    pub physical_applicability: DimensionResult,
    pub qualification: DimensionResult,
    pub checks: CheckReport,
}

fn finite_quantity(q: &Quantity, expected: Unit, label: &str, errors: &mut Vec<String>) {
    if q.unit != expected {
        errors.push(format!(
            "{label} has unit {:?}, expected {:?}",
            q.unit, expected
        ));
    }
    if !q.value.is_finite() {
        errors.push(format!("{label} is not finite"));
    }
    if q.evidence_kind == EvidenceKind::Measured {
        errors.push(format!(
            "{label} claims measured evidence without a verified importer"
        ));
    }
    if q.source.trim().is_empty() || q.applicability.trim().is_empty() {
        errors.push(format!("{label} lacks source or applicability"));
    }
    if q.test_conditions.is_empty() {
        errors.push(format!("{label} lacks test conditions"));
    }
}

fn evidence_ok(e: &EvidenceRef, label: &str, errors: &mut Vec<String>) {
    if e.kind == EvidenceKind::Measured {
        errors.push(format!("{label} claims measured evidence without a verified importer"));
    }
    if e.source.trim().is_empty() || e.applicability.trim().is_empty() {
        errors.push(format!("{label} provenance is incomplete"));
    }
    if e.test_conditions.is_empty() {
        errors.push(format!("{label} has no test conditions"));
    }
    if e.stale {
        errors.push(format!("{label} is stale"));
    }
    match &e.sha256 {
        Some(hash) if hash.len() == 64 && hash.bytes().all(|b| b.is_ascii_hexdigit()) => {}
        Some(_) => errors.push(format!("{label} has malformed SHA-256")),
        None if label == "independent reference" => {
            errors.push(format!("{label} requires a pinned SHA-256"))
        }
        None => {}
    }
}

/// Evaluate the assurance contract.  The caller supplies the actual values;
/// this function never turns a citation, hash, or sensitivity point into a
/// physical bound by itself.
pub fn assess(input: &AssuranceInput) -> ModelAssuranceReport {
    let mut errors = Vec::new();
    evidence_ok(&input.source_provenance, "source", &mut errors);
    finite_quantity(&input.nominal_line_rms, Unit::Volt, "line RMS", &mut errors);
    finite_quantity(
        &input.nominal_current_rms,
        Unit::Amp,
        "current RMS",
        &mut errors,
    );
    finite_quantity(&input.gate_drive, Unit::Volt, "gate drive", &mut errors);
    if input.nominal_line_rms.value <= 0.0 || input.nominal_current_rms.value <= 0.0 {
        errors.push("nominal line/current must be positive".into());
    }
    if (input.nominal_line_rms.value - NOMINAL_LINE_RMS_V).abs() > 1e-9 {
        errors.push(format!(
            "nominal line RMS {:.6} V differs from authored {:.6} V",
            input.nominal_line_rms.value, NOMINAL_LINE_RMS_V
        ));
    }
    if (input.nominal_current_rms.value - NOMINAL_CURRENT_RMS_A).abs() > 1e-9 {
        errors.push(format!(
            "nominal current RMS {:.6} A differs from authored {:.6} A",
            input.nominal_current_rms.value, NOMINAL_CURRENT_RMS_A
        ));
    }
    let mut classes = std::collections::BTreeSet::new();
    let mut keys = std::collections::BTreeSet::new();
    for term in &input.terms {
        finite_quantity(&term.value, Unit::Watt, &term.name, &mut errors);
        if term.value.value < 0.0 {
            errors.push(format!("{} is negative", term.name));
        }
        if !keys.insert(term.disjoint_key.clone()) {
            errors.push(format!("loss term {} is duplicated", term.name));
        }
        if !classes.insert(term.class) {
            errors.push(format!("loss term class {:?} is duplicated", term.class));
        }
    }
    for required in [
        TermClass::SwitchingOverlap,
        TermClass::OutputCapacitance,
        TermClass::Conduction,
        TermClass::GateNetwork,
    ] {
        if !classes.contains(&required) {
            errors.push(format!("loss term class {:?} is omitted", required));
        }
    }
    for (class, name, key) in [
        (
            TermClass::SwitchingOverlap,
            "switching_overlap",
            "mosfet.switching.overlap",
        ),
        (
            TermClass::OutputCapacitance,
            "output_capacitance",
            "mosfet.switching.eoss",
        ),
        (TermClass::Conduction, "conduction", "mosfet.conduction"),
        (TermClass::GateNetwork, "gate_network", "gate.network"),
    ] {
        if !input
            .terms
            .iter()
            .any(|term| term.class == class && term.name == name && term.disjoint_key == key)
        {
            errors.push(format!(
                "loss term {:?} does not match canonical ownership",
                class
            ));
        }
    }
    if input
        .unknowns
        .iter()
        .any(|u| u.name.trim().is_empty() || u.reason.trim().is_empty())
    {
        errors.push("unknown terms require a name and reason".into());
    }
    match &input.independent_reference {
        None => {
            errors.push("independent reference comparison is required".into());
        }
        Some(r) => {
            evidence_ok(&r.evidence, "independent reference", &mut errors);
            finite_quantity(&r.reference, Unit::Joule, "reference value", &mut errors);
            finite_quantity(&r.observed, Unit::Joule, "observed value", &mut errors);
            if r.evidence.kind != EvidenceKind::IndependentReference {
                errors.push("reference evidence is not independent".into());
            }
            if !r.tolerance.is_finite() || r.tolerance < 0.0 {
                errors.push("reference tolerance must be finite and nonnegative".into());
            } else if (r.reference.value - r.observed.value).abs() > r.tolerance {
                errors.push(format!(
                    "independent reference mismatch: {:.9} J vs {:.9} J (tol {:.9} J)",
                    r.reference.value, r.observed.value, r.tolerance
                ));
            }
        }
    }
    let numerical_status = if errors.is_empty() {
        Status::Pass
    } else {
        Status::Fail
    };
    let numerical = DimensionResult {
        status: numerical_status,
        rationale: if errors.is_empty() {
            "typed inputs, disjoint terms, provenance, and independent reference agree".into()
        } else {
            errors.join("; ")
        },
        unknowns: input.unknowns.iter().map(|u| u.name.clone()).collect(),
    };
    let physical_unknowns: Vec<_> = input
        .unknowns
        .iter()
        .filter(|u| u.may_change_outcome)
        .map(|u| format!("{}: {}", u.name, u.reason))
        .collect();
    let physical_status = if !errors.is_empty() {
        Status::Fail
    } else {
        // This sensitivity adapter has no importer for measured gate and
        // thermal evidence.  Keep applicability indeterminate by construction.
        Status::Indeterminate
    };
    let physical = DimensionResult {
        status: physical_status,
        rationale: "sensitivity model has no verified physical-evidence importer; applicability remains indeterminate".into(),
        unknowns: physical_unknowns,
    };
    let qualification_status = if !errors.is_empty() {
        Status::Fail
    } else {
        // A numerical replay has no authority to qualify powered hardware.
        Status::Indeterminate
    };
    let qualification = DimensionResult {
        status: qualification_status,
        rationale: "numerical replay does not qualify powered hardware".into(),
        unknowns: vec!["hardware qualification and installed conditions".into()],
    };
    let findings = vec![
        match numerical.status {
            Status::Pass => Finding::pass(RULES[0], numerical.rationale.clone(), "pfc-loss-model"),
            Status::Fail => Finding::fail(RULES[0], numerical.rationale.clone(), "pfc-loss-model"),
            Status::Indeterminate => {
                Finding::indeterminate(RULES[0], numerical.rationale.clone(), "pfc-loss-model")
            }
        },
        match physical.status {
            Status::Pass => Finding::pass(RULES[1], physical.rationale.clone(), "pfc-loss-model"),
            Status::Fail => Finding::fail(RULES[1], physical.rationale.clone(), "pfc-loss-model"),
            Status::Indeterminate => {
                Finding::indeterminate(RULES[1], physical.rationale.clone(), "pfc-loss-model")
            }
        },
        match qualification.status {
            Status::Pass => {
                Finding::pass(RULES[2], qualification.rationale.clone(), "pfc-loss-model")
            }
            Status::Fail => {
                Finding::fail(RULES[2], qualification.rationale.clone(), "pfc-loss-model")
            }
            Status::Indeterminate => {
                Finding::indeterminate(RULES[2], qualification.rationale.clone(), "pfc-loss-model")
            }
        },
    ];
    ModelAssuranceReport {
        numerical_verification: numerical,
        physical_applicability: physical,
        qualification,
        checks: CheckReport::from_findings(findings, RULES.map(str::to_owned).to_vec(), Vec::new()),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn q(value: f64, unit: Unit, source: &str, kind: EvidenceKind) -> Quantity {
        Quantity {
            value,
            unit,
            source: source.into(),
            evidence_kind: kind,
            test_conditions: vec!["120 Vrms, 15 Arms, 389.6 V bus".into()],
            applicability: "synthetic PFC replay".into(),
            unknowns: Vec::new(),
        }
    }
    fn evidence(kind: EvidenceKind) -> EvidenceRef {
        EvidenceRef {
            source: "power-entry/loss-budget/options/harness/triangle-anchor.json".into(),
            sha256: Some("a".repeat(64)),
            kind,
            test_conditions: vec!["400 V, 10 A, 20 ns + 30 ns".into()],
            applicability: "clamped-inductive anchor".into(),
            stale: false,
        }
    }
    fn input() -> AssuranceInput {
        AssuranceInput {
            source_provenance: evidence(EvidenceKind::Derived),
            nominal_line_rms: q(120.0, Unit::Volt, "source", EvidenceKind::Derived),
            nominal_current_rms: q(15.0, Unit::Amp, "source", EvidenceKind::Derived),
            gate_drive: q(10.0, Unit::Volt, "assumption", EvidenceKind::Assumption),
            terms: vec![
                ("switching_overlap", TermClass::SwitchingOverlap),
                ("output_capacitance", TermClass::OutputCapacitance),
                ("conduction", TermClass::Conduction),
                ("gate_network", TermClass::GateNetwork),
            ]
            .into_iter()
            .map(|(name, class)| LossTerm {
                name: name.into(),
                class,
                value: q(1.0, Unit::Watt, "model", EvidenceKind::Derived),
                disjoint_key: match class {
                    TermClass::SwitchingOverlap => "mosfet.switching.overlap",
                    TermClass::OutputCapacitance => "mosfet.switching.eoss",
                    TermClass::Conduction => "mosfet.conduction",
                    TermClass::GateNetwork => "gate.network",
                }
                .into(),
            })
            .collect(),
            unknowns: vec![UnknownTerm {
                name: "Eon/Eoff applicability".into(),
                reason: "no measured waveform".into(),
                may_change_outcome: true,
            }],
            independent_reference: Some(IndependentReference {
                evidence: evidence(EvidenceKind::IndependentReference),
                reference: q(
                    100e-6,
                    Unit::Joule,
                    "retained reference",
                    EvidenceKind::IndependentReference,
                ),
                observed: q(100e-6, Unit::Joule, "quadrature", EvidenceKind::Derived),
                tolerance: 1e-9,
            }),
        }
    }

    #[test]
    fn supported_synthetic_pass_has_three_separate_dimensions() {
        let mut i = input();
        i.unknowns.clear();
        let r = assess(&i);
        assert_eq!(r.numerical_verification.status, Status::Pass);
        assert_eq!(r.qualification.status, Status::Indeterminate);
        assert_eq!(r.physical_applicability.status, Status::Indeterminate);
    }
    #[test]
    fn unsupported_inputs_are_indeterminate_but_numerics_can_pass() {
        let r = assess(&input());
        assert_eq!(r.numerical_verification.status, Status::Pass);
        assert_eq!(r.physical_applicability.status, Status::Indeterminate);
        assert_eq!(r.qualification.status, Status::Indeterminate);
    }
    #[test]
    fn corrupt_adapter_cannot_accept_reference_or_terms() {
        let mut i = input();
        i.independent_reference.as_mut().unwrap().observed.value = 0.0;
        i.terms.pop();
        let r = assess(&i);
        assert_eq!(r.checks.status, Status::Fail);
        assert_eq!(r.numerical_verification.status, Status::Fail);
    }
    #[test]
    fn wrong_nominal_current_cannot_become_decision_input() {
        let mut i = input();
        i.nominal_current_rms.value = 14.0;
        let r = assess(&i);
        assert_eq!(r.numerical_verification.status, Status::Fail);
    }
    #[test]
    fn missing_provenance_stale_evidence_and_missing_reference_fail_closed() {
        let mut missing = input();
        missing.source_provenance.source.clear();
        assert_eq!(assess(&missing).numerical_verification.status, Status::Fail);
        let mut stale = input();
        stale.independent_reference.as_mut().unwrap().evidence.stale = true;
        assert_eq!(assess(&stale).numerical_verification.status, Status::Fail);
        let mut absent = input();
        absent.independent_reference = None;
        assert_eq!(assess(&absent).numerical_verification.status, Status::Fail);
    }
    #[test]
    fn duplicate_owned_term_cannot_be_hidden_by_a_new_label() {
        let mut i = input();
        i.terms.push(i.terms[0].clone());
        i.terms.last_mut().unwrap().name = "renamed_overlap".into();
        assert_eq!(assess(&i).numerical_verification.status, Status::Fail);
    }
    #[test]
    fn fake_measured_label_without_importer_cannot_pass() {
        let mut i = input();
        i.nominal_line_rms.evidence_kind = EvidenceKind::Measured;
        assert_eq!(assess(&i).numerical_verification.status, Status::Fail);
    }
    #[test]
    fn gate_assumption_is_not_actual_qualification() {
        let mut i = input();
        i.unknowns.push(UnknownTerm {
            name: "gate waveform".into(),
            reason: "assumed bias".into(),
            may_change_outcome: true,
        });
        let r = assess(&i);
        assert_eq!(r.physical_applicability.status, Status::Indeterminate);
    }
}
