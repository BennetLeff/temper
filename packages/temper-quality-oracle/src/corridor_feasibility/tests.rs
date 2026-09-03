//! Unit tests for the corridor feasibility protocol.

use super::*;
use crate::regional_feasibility::{CORRIDOR_VALIDATED_SCREEN_SCHEMA, RawCorridorMeasurements};

fn check(
    evaluation: EvaluationState,
    trust: TrustState,
    findings: Vec<FindingIdentity>,
    receipt: Option<&str>,
) -> CheckEvidence {
    let mut check = CheckEvidence {
        evaluation,
        trust,
        findings,
        receipt_sha256: receipt.map(str::to_owned),
        evidence_payload_sha256: None,
    };
    if evaluation != EvaluationState::NotEvaluated {
        check.evidence_payload_sha256 = Some(check_payload_sha256(&check).unwrap());
    }
    check
}
#[cfg_attr(test, test)]
fn not_evaluated_netlist_is_not_a_veto() {
    let empty = CheckEvidence {
        evaluation: EvaluationState::NotEvaluated,
        trust: TrustState::Indeterminate,
        findings: Vec::new(),
        receipt_sha256: None,
        evidence_payload_sha256: None,
    };
    let e = PreRouteEvidence {
        safety: empty.clone(),
        drc: empty.clone(),
        containment: empty.clone(),
        body_overlap: empty.clone(),
        courtyard_overlap: empty.clone(),
        connectivity: empty.clone(),
        route_geometry: empty.clone(),
        current_capacity: empty.clone(),
        selv_denominator: empty.clone(),
        mutation_scope: empty.clone(),
        netlist_reconciliation: empty,
    };
    validate_pre_route_evidence(&e).unwrap();
    assert!(
        summarize_findings(&canonical_findings(&e))
            .vetoes
            .is_empty()
    );
}
#[cfg_attr(test, test)]
fn same_count_identity_substitution_remains_a_veto() {
    let f = vec![FindingIdentity {
        category: FindingCategory::Drc,
        identity: "clearance:old->new".into(),
        multiplicity: 5,
    }];
    let s = summarize_findings(&f);
    assert_eq!(s.total, 5);
    assert_eq!(s.by_category[&FindingCategory::Drc], 5);
    assert!(!s.vetoes.is_empty());
}

#[cfg_attr(test, test)]
fn evidence_payload_digest_binds_exact_identity_and_multiplicity() {
    let mut evidence = check(
        EvaluationState::CompletedWithFindings,
        TrustState::Trusted,
        vec![FindingIdentity {
            category: FindingCategory::Drc,
            identity: "clearance:A:B".into(),
            multiplicity: 2,
        }],
        Some(&"a".repeat(64)),
    );
    validate_check("drc", &evidence).unwrap();
    evidence.findings[0].multiplicity = 3;
    assert!(validate_check("drc", &evidence).is_err());
}

#[cfg_attr(test, test)]
fn seal_helper_is_write_once_and_rust_owned() {
    let mut unsealed = check(
        EvaluationState::CompletedClean,
        TrustState::Trusted,
        vec![],
        Some(&"a".repeat(64)),
    );
    unsealed.evidence_payload_sha256 = None;
    let sealed = seal_check_evidence(unsealed.clone()).unwrap();
    assert!(sealed.evidence_payload_sha256.is_some());
    assert_eq!(
        seal_check_evidence(sealed).unwrap_err(),
        "check evidence is already sealed"
    );
    let mut forged = unsealed;
    forged.evidence_payload_sha256 = Some("b".repeat(64));
    assert!(seal_check_evidence(forged).is_err());
}

#[cfg_attr(test, test)]
fn tampered_witness_to_another_valid_candidate_is_rejected() {
    let ordered = vec!["candidate-1".into(), "candidate-2".into()];
    assert!(require_first_screen_witness("candidate-1", &ordered).is_ok());
    let error = require_first_screen_witness("candidate-2", &ordered).unwrap_err();
    assert!(error.contains("candidate-1"));
}

#[cfg_attr(test, test)]
fn diagnostics_are_rust_owned_and_conservative() {
    let missing = FindingIdentity {
        category: FindingCategory::ContainmentMissingModel,
        identity: "J1:body_geometry".into(),
        multiplicity: 1,
    };
    let route = FindingIdentity {
        category: FindingCategory::GateFailure,
        identity: "route-shape".into(),
        multiplicity: 4,
    };
    let family = diagnostic_for("containment", &missing);
    assert_eq!(family.dependency, FindingDependency::FamilyInvariant);
    assert!(family.candidate_dimensions.is_empty());
    let shape = diagnostic_for("route_geometry", &route);
    assert_eq!(shape.dependency, FindingDependency::RouteShapeDependent);
    assert_eq!(shape.candidate_dimensions, vec!["route-shape"]);
    let denominator = diagnostic_for("selv_denominator", &route);
    assert_eq!(denominator.dependency, FindingDependency::Unresolved);
    assert_eq!(
        denominator.candidate_dimensions,
        vec!["placement", "route-shape"]
    );
}

#[cfg_attr(test, test)]
fn indeterminate_instrument_preserves_completed_sealed_findings() {
    let clean = || {
        check(
            EvaluationState::CompletedClean,
            TrustState::Trusted,
            vec![],
            Some(&"a".repeat(64)),
        )
    };
    let finding = FindingIdentity {
        category: FindingCategory::Drc,
        identity: "clearance:indeterminate-report".into(),
        multiplicity: 2,
    };
    let mut evidence = PreRouteEvidence {
        safety: clean(),
        drc: check(
            EvaluationState::CompletedWithFindings,
            TrustState::Indeterminate,
            vec![finding],
            Some(&"b".repeat(64)),
        ),
        containment: clean(),
        body_overlap: clean(),
        courtyard_overlap: clean(),
        connectivity: clean(),
        route_geometry: clean(),
        current_capacity: clean(),
        selv_denominator: clean(),
        mutation_scope: clean(),
        netlist_reconciliation: CheckEvidence {
            evaluation: EvaluationState::NotEvaluated,
            trust: TrustState::Indeterminate,
            findings: vec![],
            receipt_sha256: None,
            evidence_payload_sha256: None,
        },
    };
    validate_pre_route_evidence(&evidence).unwrap();
    let names = [
        ("safety-signatures", InstrumentState::Trusted),
        ("normalized-kicad-drc", InstrumentState::Indeterminate),
        ("containment", InstrumentState::Trusted),
        ("body-courtyard-overlap", InstrumentState::Trusted),
        ("connectivity", InstrumentState::Trusted),
        ("route-geometry-current-capacity", InstrumentState::Trusted),
        ("selv-denominator", InstrumentState::Trusted),
        ("mutation-scope", InstrumentState::Trusted),
    ];
    let subject = "c".repeat(64);
    let instruments = names
        .iter()
        .map(|(name, state)| InstrumentEvidence {
            name: (*name).into(),
            state: *state,
            detail: "bound".into(),
            subject_sha256: subject.clone(),
            receipt_sha256: if *name == "normalized-kicad-drc" {
                "b".repeat(64)
            } else {
                "a".repeat(64)
            },
        })
        .collect::<Vec<_>>();
    validate_check_instrument_bindings(&evidence, &instruments).unwrap();
    assert_eq!(
        evidence.drc.evaluation,
        EvaluationState::CompletedWithFindings
    );
    assert_eq!(evidence.drc.trust, TrustState::Indeterminate);
    assert!(evidence.drc.evidence_payload_sha256.is_some());

    let mut tampered_receipt = evidence.clone();
    tampered_receipt.drc.receipt_sha256 = Some("e".repeat(64));
    tampered_receipt.drc.evidence_payload_sha256 =
        Some(check_payload_sha256(&tampered_receipt.drc).unwrap());
    assert!(validate_check_instrument_bindings(&tampered_receipt, &instruments).is_err());

    // A later caller cannot turn this into a post-route error: error
    // instruments remain the distinct NotEvaluated + Error state.
    evidence.drc = CheckEvidence {
        evaluation: EvaluationState::NotEvaluated,
        trust: TrustState::Error,
        findings: vec![],
        receipt_sha256: Some("d".repeat(64)),
        evidence_payload_sha256: None,
    };
    assert!(validate_check("drc", &evidence.drc).is_ok());
    assert!(validate_check_instrument_bindings(&evidence, &instruments).is_err());
}

#[cfg_attr(test, test)]
fn terminal_precedence_never_hides_instrument_uncertainty() {
    let finding = vec![FindingIdentity {
        category: FindingCategory::Safety,
        identity: "safety-1".into(),
        multiplicity: 1,
    }];
    assert_eq!(
        finalize_terminal(InstrumentState::Error, &finding).0,
        FeasibilityTerminal::InstrumentError
    );
    assert_eq!(
        finalize_terminal(InstrumentState::Indeterminate, &finding).0,
        FeasibilityTerminal::StoppedIndeterminate
    );
    assert_eq!(
        finalize_terminal(InstrumentState::Trusted, &finding).0,
        FeasibilityTerminal::WitnessRejected
    );
    assert_eq!(
        finalize_terminal(InstrumentState::Trusted, &[]).0,
        FeasibilityTerminal::WitnessClean
    );
}
#[cfg_attr(test, test)]
fn singleton_finding_has_no_family_certificate_surface() {
    let json = r#"{"category":"safety","identity":"one","multiplicity":1,"dependency":"family-invariant"}"#;
    assert!(serde_json::from_str::<FindingIdentity>(json).is_err());
}

#[cfg_attr(test, test)]
fn feasibility_request_rejects_unknown_or_downgrade_schema() {
    assert!(serde_json::from_str::<FeasibilityTerminal>(r#""witness-clean-v0""#).is_err());
    let extra = r#"{"schema_version":"temper-corridor-feasibility-prepare/v1","screening":null,"authorities":null,"model_requirements":[],"preflight":[],"legacy_terminal":"witness-clean"}"#;
    assert!(serde_json::from_str::<PrepareRequest>(extra).is_err());
}

#[cfg_attr(test, test)]
fn impossible_lifecycle_payloads_fail_closed() {
    let finding = FindingIdentity {
        category: FindingCategory::Safety,
        identity: "s1".into(),
        multiplicity: 1,
    };
    assert!(
        validate_check(
            "safety",
            &check(
                EvaluationState::NotEvaluated,
                TrustState::Trusted,
                vec![],
                None
            )
        )
        .is_err()
    );
    assert!(
        validate_check(
            "safety",
            &check(
                EvaluationState::NotEvaluated,
                TrustState::Indeterminate,
                vec![],
                Some(&"a".repeat(64))
            )
        )
        .is_err()
    );
    assert!(
        validate_check(
            "safety",
            &check(
                EvaluationState::CompletedClean,
                TrustState::Trusted,
                vec![finding.clone()],
                Some(&"a".repeat(64))
            )
        )
        .is_err()
    );
    assert!(
        validate_check(
            "safety",
            &check(
                EvaluationState::CompletedWithFindings,
                TrustState::Trusted,
                vec![],
                Some(&"a".repeat(64))
            )
        )
        .is_err()
    );
    assert!(
        validate_check(
            "safety",
            &check(
                EvaluationState::NotEvaluated,
                TrustState::Error,
                vec![],
                None
            )
        )
        .is_err()
    );
    assert!(
        validate_check(
            "safety",
            &check(
                EvaluationState::NotEvaluated,
                TrustState::Error,
                vec![],
                Some(&"a".repeat(64))
            )
        )
        .is_ok()
    );
    assert!(
        validate_check(
            "safety",
            &check(
                EvaluationState::CompletedWithFindings,
                TrustState::Error,
                vec![finding],
                Some(&"a".repeat(64))
            )
        )
        .is_ok()
    );
}

#[cfg_attr(test, test)]
fn finding_categories_are_bound_to_their_check() {
    let wrong = FindingIdentity {
        category: FindingCategory::Drc,
        identity: "d1".into(),
        multiplicity: 1,
    };
    assert!(
        validate_check(
            "safety",
            &check(
                EvaluationState::CompletedWithFindings,
                TrustState::Trusted,
                vec![wrong],
                Some(&"a".repeat(64))
            )
        )
        .is_err()
    );
    let outside = FindingIdentity {
        category: FindingCategory::ContainmentOutsideBoard,
        identity: "J1".into(),
        multiplicity: 1,
    };
    assert!(
        validate_check(
            "containment",
            &check(
                EvaluationState::CompletedWithFindings,
                TrustState::Trusted,
                vec![outside],
                Some(&"a".repeat(64))
            )
        )
        .is_ok()
    );
}

#[cfg_attr(test, test)]
fn canonical_summary_preserves_multiplicity_and_order() {
    let e = PreRouteEvidence {
        safety: check(
            EvaluationState::CompletedWithFindings,
            TrustState::Trusted,
            vec![FindingIdentity {
                category: FindingCategory::Safety,
                identity: "z".into(),
                multiplicity: 2,
            }],
            Some(&"a".repeat(64)),
        ),
        drc: check(
            EvaluationState::CompletedWithFindings,
            TrustState::Trusted,
            vec![FindingIdentity {
                category: FindingCategory::Drc,
                identity: "a".into(),
                multiplicity: 3,
            }],
            Some(&"b".repeat(64)),
        ),
        containment: check(
            EvaluationState::CompletedClean,
            TrustState::Trusted,
            vec![],
            Some(&"c".repeat(64)),
        ),
        body_overlap: check(
            EvaluationState::CompletedClean,
            TrustState::Trusted,
            vec![],
            Some(&"d".repeat(64)),
        ),
        courtyard_overlap: check(
            EvaluationState::CompletedClean,
            TrustState::Trusted,
            vec![],
            Some(&"e".repeat(64)),
        ),
        connectivity: check(
            EvaluationState::CompletedClean,
            TrustState::Trusted,
            vec![],
            Some(&"f".repeat(64)),
        ),
        route_geometry: check(
            EvaluationState::CompletedClean,
            TrustState::Trusted,
            vec![],
            Some(&"0".repeat(64)),
        ),
        current_capacity: check(
            EvaluationState::CompletedClean,
            TrustState::Trusted,
            vec![],
            Some(&"0".repeat(64)),
        ),
        selv_denominator: check(
            EvaluationState::CompletedClean,
            TrustState::Trusted,
            vec![],
            Some(&"2".repeat(64)),
        ),
        mutation_scope: check(
            EvaluationState::CompletedClean,
            TrustState::Trusted,
            vec![],
            Some(&"1".repeat(64)),
        ),
        netlist_reconciliation: check(
            EvaluationState::NotEvaluated,
            TrustState::Indeterminate,
            vec![],
            None,
        ),
    };
    validate_pre_route_evidence(&e).unwrap();
    let findings = canonical_findings(&e);
    assert_eq!(findings[0].category, FindingCategory::Safety);
    assert_eq!(summarize_findings(&findings).total, 5);
}

#[cfg_attr(test, test)]
fn preflight_order_is_part_of_the_exact_instrument_set() {
    let subject = "a".repeat(64);
    let names = [
        "pcbnew-rotation-oracle",
        "baseline-kicad-drc",
        "pyo3-extensions",
    ];
    let rows = names
        .iter()
        .enumerate()
        .map(|(i, name)| InstrumentEvidence {
            name: (*name).into(),
            state: InstrumentState::Trusted,
            detail: "ok".into(),
            subject_sha256: subject.clone(),
            receipt_sha256: format!("{:064x}", i + 1),
        })
        .collect::<Vec<_>>();
    assert!(validate_preflight(&rows, &subject).is_err());
}

#[cfg_attr(test, test)]
fn family_negative_has_no_unregistered_caller_assertion() {
    // No terminal or request field can assert FamilyNegative. Until a
    // sound Rust predicate is registered, prepare can only produce
    // model/instrument/stopped/witness terminals.
    let json =
        r#"{"schema_version":"temper-corridor-feasibility-prepare/v1","family_negative":true}"#;
    assert!(serde_json::from_str::<PrepareRequest>(json).is_err());
    assert!(serde_json::from_str::<FeasibilityTerminal>(r#""family-negative""#).is_err());
}

#[cfg_attr(test, test)]
fn scratch_subject_cannot_be_the_production_board() {
    let board = "a".repeat(64);
    assert!(validate_scratch_board_subject(&board, &board).is_err());
    assert!(validate_scratch_board_subject(&"b".repeat(64), &board).is_ok());
}

#[cfg_attr(test, test)]
fn prepare_and_finalize_real_corridor_evidence_lifecycle() {
    const DECLARATION: &str = include_str!(
        "../../../../docs/evidence/net41-route-layer-corridor-20260831/declaration.json"
    );
    const BASIS: &str = include_str!(
        "../../../../docs/evidence/net41-route-layer-corridor-20260831/design-basis.json"
    );
    const BOARD: &str = include_str!("../../../../pcb/temper.kicad_pcb");
    const PREDECESSOR_RECEIPT: &str = include_str!(
        "../../../../docs/evidence/r14-hv-domain-refloorplan-20260831/terminal-receipt.json"
    );
    const PREDECESSOR_MANIFEST: &str = include_str!(
        "../../../../docs/evidence/r14-hv-domain-refloorplan-20260831/pre-route-manifest.json"
    );
    const DOMAIN_MANIFEST: &str = include_str!("../../../../elec/domain_manifest.yaml");
    const NETLIST: &str = include_str!("../../../../elec/build/default.net");
    const KICAD_DRU: &str = include_str!("../../../../pcb/temper.kicad_dru");
    const FEASIBILITY_MANIFEST: &str = include_str!(
        "../../../../docs/evidence/net41-corridor-feasibility-20260902/feasibility-manifest.json"
    );
    const CAMPAIGN_MANIFEST: &str = include_str!(
        "../../../../docs/evidence/net41-corridor-execution-20260901/candidate-manifest.json"
    );

    let evidence = CorridorEvidenceInputs {
        declaration_json: DECLARATION,
        basis_json: BASIS,
        board_text: BOARD,
        predecessor_receipt_json: PREDECESSOR_RECEIPT,
        predecessor_manifest_json: PREDECESSOR_MANIFEST,
        domain_manifest_text: DOMAIN_MANIFEST,
        netlist_text: NETLIST,
        kicad_dru_text: KICAD_DRU,
    };
    let feasibility_manifest: serde_json::Value =
        serde_json::from_str(FEASIBILITY_MANIFEST).expect("valid feasibility manifest");
    let campaign_manifest: serde_json::Value =
        serde_json::from_str(CAMPAIGN_MANIFEST).expect("valid campaign manifest");
    let measurements = campaign_manifest["screen_results"]
        .as_array()
        .expect("screen results")
        .iter()
        .map(|row| {
            serde_json::from_value::<RawCorridorMeasurements>(row["raw_measurements"].clone())
                .expect("typed candidate measurement")
        })
        .collect();
    let screening = CorridorValidatedScreenRequest {
        schema_version: CORRIDOR_VALIDATED_SCREEN_SCHEMA.into(),
        candidates: measurements,
        route_budget: 1,
    };
    let authorities = serde_json::from_value::<FeasibilityAuthorities>(
        feasibility_manifest["authorities"].clone(),
    )
    .expect("typed authorities");
    let model_requirements = serde_json::from_value::<Vec<ModelRequirementRow>>(
        feasibility_manifest["model_requirements"].clone(),
    )
    .expect("typed model requirements");
    let preflight = serde_json::from_value::<Vec<InstrumentEvidence>>(
        feasibility_manifest["preflight"].clone(),
    )
    .expect("typed preflight");
    let prepared = prepare_corridor_feasibility(
        &evidence,
        PrepareRequest {
            schema_version: FEASIBILITY_PREPARE_SCHEMA.into(),
            screening: screening.clone(),
            authorities: authorities.clone(),
            model_requirements: model_requirements.clone(),
            preflight,
        },
    )
    .expect("prepare accepts committed evidence");
    assert_eq!(prepared.terminal, FeasibilityTerminal::WitnessPending);
    let witness = prepared.witness.clone().expect("prepare selects a witness");
    let screened = validate_and_screen_corridor_evidence(&evidence, screening.clone())
        .expect("screening remains bound to the same declaration");
    assert_eq!(
        witness.candidate_id,
        screened
            .clearance_creepage_prefilter_subset
            .first()
            .expect("one Rust-ordered survivor")
            .clone()
    );

    let scratch = "f".repeat(64);
    let instrument_names = [
        "body-courtyard-overlap",
        "connectivity",
        "containment",
        "mutation-scope",
        "normalized-kicad-drc",
        "route-geometry-current-capacity",
        "safety-signatures",
        "selv-denominator",
    ];
    let instruments = instrument_names
        .iter()
        .enumerate()
        .map(|(index, name)| InstrumentEvidence {
            name: (*name).into(),
            state: InstrumentState::Trusted,
            detail: "committed lifecycle test instrument".into(),
            subject_sha256: scratch.clone(),
            receipt_sha256: format!("{:064x}", index + 1),
        })
        .collect::<Vec<_>>();
    let clean = |name: &str| {
        let receipt = instruments
            .iter()
            .find(|row| row.name == name)
            .expect("instrument receipt")
            .receipt_sha256
            .clone();
        check(
            EvaluationState::CompletedClean,
            TrustState::Trusted,
            vec![],
            Some(&receipt),
        )
    };
    let clean_evidence = || PreRouteEvidence {
        safety: clean("safety-signatures"),
        drc: clean("normalized-kicad-drc"),
        containment: clean("containment"),
        body_overlap: clean("body-courtyard-overlap"),
        courtyard_overlap: clean("body-courtyard-overlap"),
        connectivity: clean("connectivity"),
        route_geometry: clean("route-geometry-current-capacity"),
        current_capacity: clean("route-geometry-current-capacity"),
        selv_denominator: clean("selv-denominator"),
        mutation_scope: clean("mutation-scope"),
        netlist_reconciliation: CheckEvidence {
            evaluation: EvaluationState::NotEvaluated,
            trust: TrustState::Indeterminate,
            findings: vec![],
            receipt_sha256: None,
            evidence_payload_sha256: None,
        },
    };
    let make_request =
        |evidence: PreRouteEvidence, instruments: Vec<InstrumentEvidence>| FinalizeRequest {
            schema_version: FEASIBILITY_FINALIZE_SCHEMA.into(),
            prepared: prepared.clone(),
            authorities: authorities.clone(),
            model_requirements: model_requirements.clone(),
            screening: screening.clone(),
            witness_id: witness.witness_id.clone(),
            declaration_ordinal: witness.declaration_ordinal,
            materialization_instruction: witness.materialization_instruction.clone(),
            scratch_board_sha256: scratch.clone(),
            instruments,
            evidence,
        };

    let clean_receipt = finalize_corridor_feasibility(
        &evidence,
        make_request(clean_evidence(), instruments.clone()),
    )
    .expect("finalize accepts a complete clean witness");
    assert_eq!(clean_receipt.terminal, FeasibilityTerminal::WitnessClean);

    let mut finding_evidence = clean_evidence();
    finding_evidence.safety = check(
        EvaluationState::CompletedWithFindings,
        TrustState::Trusted,
        vec![FindingIdentity {
            category: FindingCategory::Safety,
            identity: "test-safety-finding".into(),
            multiplicity: 1,
        }],
        Some(&instruments[6].receipt_sha256),
    );
    let finding_receipt = finalize_corridor_feasibility(
        &evidence,
        make_request(finding_evidence, instruments.clone()),
    )
    .expect("finalize preserves exact findings");
    assert_eq!(
        finding_receipt.terminal,
        FeasibilityTerminal::WitnessRejected
    );

    let mut tampered_witness = make_request(clean_evidence(), instruments.clone());
    tampered_witness.witness_id.push('x');
    assert!(finalize_corridor_feasibility(&evidence, tampered_witness).is_err());
    let mut tampered_instrument = instruments.clone();
    tampered_instrument[0].receipt_sha256 = "e".repeat(64);
    assert!(
        finalize_corridor_feasibility(
            &evidence,
            make_request(clean_evidence(), tampered_instrument)
        )
        .is_err()
    );
}

// --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
/// Every `#[test]` in this module, as a callable the `wasm32`
/// entry point can invoke by index.  Generated because these
/// functions are private to this module and unreachable from
/// anywhere a registry could otherwise live.
pub const WASM_TESTS: &[(&str, fn())] = &[
    ("corridor_feasibility::tests::not_evaluated_netlist_is_not_a_veto", not_evaluated_netlist_is_not_a_veto),
    ("corridor_feasibility::tests::same_count_identity_substitution_remains_a_veto", same_count_identity_substitution_remains_a_veto),
    ("corridor_feasibility::tests::evidence_payload_digest_binds_exact_identity_and_multiplicity", evidence_payload_digest_binds_exact_identity_and_multiplicity),
    ("corridor_feasibility::tests::seal_helper_is_write_once_and_rust_owned", seal_helper_is_write_once_and_rust_owned),
    ("corridor_feasibility::tests::tampered_witness_to_another_valid_candidate_is_rejected", tampered_witness_to_another_valid_candidate_is_rejected),
    ("corridor_feasibility::tests::diagnostics_are_rust_owned_and_conservative", diagnostics_are_rust_owned_and_conservative),
    ("corridor_feasibility::tests::indeterminate_instrument_preserves_completed_sealed_findings", indeterminate_instrument_preserves_completed_sealed_findings),
    ("corridor_feasibility::tests::terminal_precedence_never_hides_instrument_uncertainty", terminal_precedence_never_hides_instrument_uncertainty),
    ("corridor_feasibility::tests::singleton_finding_has_no_family_certificate_surface", singleton_finding_has_no_family_certificate_surface),
    ("corridor_feasibility::tests::feasibility_request_rejects_unknown_or_downgrade_schema", feasibility_request_rejects_unknown_or_downgrade_schema),
    ("corridor_feasibility::tests::impossible_lifecycle_payloads_fail_closed", impossible_lifecycle_payloads_fail_closed),
    ("corridor_feasibility::tests::finding_categories_are_bound_to_their_check", finding_categories_are_bound_to_their_check),
    ("corridor_feasibility::tests::canonical_summary_preserves_multiplicity_and_order", canonical_summary_preserves_multiplicity_and_order),
    ("corridor_feasibility::tests::preflight_order_is_part_of_the_exact_instrument_set", preflight_order_is_part_of_the_exact_instrument_set),
    ("corridor_feasibility::tests::family_negative_has_no_unregistered_caller_assertion", family_negative_has_no_unregistered_caller_assertion),
    ("corridor_feasibility::tests::scratch_subject_cannot_be_the_production_board", scratch_subject_cannot_be_the_production_board),
    ("corridor_feasibility::tests::prepare_and_finalize_real_corridor_evidence_lifecycle", prepare_and_finalize_real_corridor_evidence_lifecycle),
];
// --- END generated by scripts/gen_wasm_test_registry.py: tests ---
