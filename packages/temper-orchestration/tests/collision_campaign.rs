use temper_geometry::rotation_quadrant::RotationQuadrant;
use temper_orchestration::collision_campaign::{
    AuditGates, CampaignError, CampaignLimits, CollisionWitness, ComponentRef, ExactPose,
    GateOutcome, InputIdentity, ModelCoordinate, Prepared, TerminalVerdict,
};

fn identity() -> InputIdentity {
    InputIdentity::new("board-sha", "rules-sha", "solver-build", "axis-x").unwrap()
}

fn limits() -> CampaignLimits {
    CampaignLimits::new(4, 120_000).unwrap()
}

fn pose(x: i64, y: i64, rotation: u8) -> ExactPose {
    ExactPose::new(
        ModelCoordinate::new(x).unwrap(),
        ModelCoordinate::new(y).unwrap(),
        RotationQuadrant::from_raw(rotation as i64),
    )
    .unwrap()
}

fn prepared() -> Prepared {
    Prepared::new(identity(), vec!["U1", "R1"], limits()).unwrap()
}

#[test]
fn constructors_reject_malformed_domain_values() {
    assert!(InputIdentity::new("", "rules", "solver", "axis").is_err());
    assert!(ComponentRef::new("").is_err());
    assert!(CampaignLimits::new(0, 1).is_err());
    assert!(CampaignLimits::new(1, 0).is_err());
    assert!(ModelCoordinate::from_mm(f64::NAN).is_err());
    assert!(ExactPose::from_raw(0, 0, 4).is_err());
    assert!(CollisionWitness::new("U1", "U1", 1.0, "candidate").is_err());
    assert!(CollisionWitness::new("U1", "R1", f64::NAN, "candidate").is_err());
    assert!(CollisionWitness::new("U1", "R1", -1.0, "candidate").is_err());
    assert!(Prepared::new(identity(), vec!["U1", "U1"], limits()).is_err());
}

#[test]
fn pairs_and_cut_keys_are_canonical_and_identity_bound() {
    let witness = CollisionWitness::new("R1", "U1", 0.25, "candidate-1").unwrap();
    let first = prepared()
        .start_solving()
        .unwrap()
        .complete_candidate(vec![("U1", pose(100, 200, 0)), ("R1", pose(300, 400, 1))])
        .unwrap()
        .audit(AuditGates::all_passed(), vec![witness.clone()])
        .unwrap();
    let cut = match first {
        temper_orchestration::collision_campaign::AuditDecision::Refining(refining) => {
            refining.cuts().first().unwrap().clone()
        }
        other => panic!("expected refinement, got {other:?}"),
    };
    assert_eq!(cut.pair().first().as_str(), "R1");
    assert_eq!(cut.pair().second().as_str(), "U1");

    let reversed = prepared()
        .start_solving()
        .unwrap()
        .complete_candidate(vec![("R1", pose(300, 400, 1)), ("U1", pose(100, 200, 0))])
        .unwrap();
    let decision = reversed
        .audit(AuditGates::all_passed(), vec![witness])
        .unwrap();
    let reversed_cut = match decision {
        temper_orchestration::collision_campaign::AuditDecision::Refining(refining) => {
            refining.cuts().first().unwrap().clone()
        }
        other => panic!("expected refinement, got {other:?}"),
    };
    assert_eq!(cut.key(), reversed_cut.key());
    assert!(reversed_cut.is_from(&identity()));
}

#[test]
fn accepted_requires_all_gates_and_collision_rejection_refines() {
    let candidate = prepared()
        .start_solving()
        .unwrap()
        .complete_candidate(vec![("U1", pose(100, 200, 0)), ("R1", pose(300, 400, 1))])
        .unwrap();
    let decision = candidate.audit(AuditGates::all_passed(), vec![]).unwrap();
    assert!(matches!(
        decision,
        temper_orchestration::collision_campaign::AuditDecision::Terminal(
            TerminalVerdict::Accepted { .. }
        )
    ));

    let candidate = prepared()
        .start_solving()
        .unwrap()
        .complete_candidate(vec![("U1", pose(100, 200, 0)), ("R1", pose(300, 400, 1))])
        .unwrap();
    let decision = candidate
        .audit(
            AuditGates::new(
                GateOutcome::Rejected("creepage shortfall".into()),
                GateOutcome::Passed,
                GateOutcome::Trusted,
            ),
            vec![],
        )
        .unwrap();
    assert!(matches!(
        decision,
        temper_orchestration::collision_campaign::AuditDecision::Terminal(
            TerminalVerdict::VerifierRejected { .. }
        )
    ));

    let candidate = prepared()
        .start_solving()
        .unwrap()
        .complete_candidate(vec![("U1", pose(100, 200, 0)), ("R1", pose(300, 400, 1))])
        .unwrap();
    let witness = CollisionWitness::new("U1", "R1", 0.25, "candidate-1").unwrap();
    let decision = candidate
        .audit(
            AuditGates::new(
                GateOutcome::Passed,
                GateOutcome::Rejected("body collision".into()),
                GateOutcome::Trusted,
            ),
            vec![witness],
        )
        .unwrap();
    assert!(matches!(
        decision,
        temper_orchestration::collision_campaign::AuditDecision::Refining(_)
    ));
}

#[test]
fn collision_witness_cannot_override_failed_creepage_or_untrusted_provenance() {
    let witness = CollisionWitness::new("U1", "R1", 0.25, "candidate-1").unwrap();
    let candidate = prepared()
        .start_solving()
        .unwrap()
        .complete_candidate(vec![("U1", pose(100, 200, 0)), ("R1", pose(300, 400, 1))])
        .unwrap();
    let decision = candidate
        .audit(
            AuditGates::new(
                GateOutcome::Rejected("creepage shortfall".into()),
                GateOutcome::Rejected("body collision".into()),
                GateOutcome::Trusted,
            ),
            vec![witness.clone()],
        )
        .unwrap();
    assert!(matches!(
        decision,
        temper_orchestration::collision_campaign::AuditDecision::Terminal(
            TerminalVerdict::VerifierRejected { .. }
        )
    ));

    let candidate = prepared()
        .start_solving()
        .unwrap()
        .complete_candidate(vec![("U1", pose(100, 200, 0)), ("R1", pose(300, 400, 1))])
        .unwrap();
    let decision = candidate
        .audit(
            AuditGates::new(
                GateOutcome::Passed,
                GateOutcome::Rejected("body collision".into()),
                GateOutcome::Passed,
            ),
            vec![witness],
        )
        .unwrap();
    assert!(matches!(
        decision,
        temper_orchestration::collision_campaign::AuditDecision::Terminal(
            TerminalVerdict::VerifierRejected { .. }
        )
    ));
}

#[test]
fn duplicate_frontier_is_no_progress_and_terminal_cannot_resume() {
    let solver = prepared().start_solving().unwrap();
    let candidate = solver
        .complete_candidate(vec![("U1", pose(1, 2, 0)), ("R1", pose(3, 4, 0))])
        .unwrap();
    let witness = CollisionWitness::new("U1", "R1", 1.0, "candidate").unwrap();
    let refining = match candidate
        .audit(AuditGates::all_passed(), vec![witness.clone()])
        .unwrap()
    {
        temper_orchestration::collision_campaign::AuditDecision::Refining(value) => value,
        other => panic!("expected refinement, got {other:?}"),
    };
    let candidate = refining
        .next_round()
        .unwrap()
        .complete_candidate(vec![("U1", pose(1, 2, 0)), ("R1", pose(3, 4, 0))])
        .unwrap();
    let terminal = match candidate
        .audit(AuditGates::all_passed(), vec![witness])
        .unwrap()
    {
        temper_orchestration::collision_campaign::AuditDecision::Terminal(value) => value,
        other => panic!("expected terminal, got {other:?}"),
    };
    assert!(matches!(terminal, TerminalVerdict::NoProgress { .. }));
    assert!(terminal.resume().is_err());
}

#[test]
fn checkpoints_are_versioned_and_reject_foreign_identity() {
    let checkpoint = prepared().checkpoint();
    let bytes = checkpoint.to_bytes().unwrap();
    let restored =
        temper_orchestration::collision_campaign::CampaignCheckpoint::from_bytes(&bytes).unwrap();
    assert!(restored.restore_for(&identity()).is_ok());
    let foreign = InputIdentity::new("other-board", "rules-sha", "solver-build", "axis-x").unwrap();
    assert!(matches!(
        restored.restore_for(&foreign),
        Err(CampaignError::ForeignIdentity { .. })
    ));
    let mut corrupt = bytes;
    corrupt[0] ^= 0xff;
    assert!(
        temper_orchestration::collision_campaign::CampaignCheckpoint::from_bytes(&corrupt).is_err()
    );
}
