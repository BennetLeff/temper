use serde_json::{json, Value};
use temper_geometry::rotation_quadrant::RotationQuadrant;
use temper_orchestration::collision_campaign::{
    AuditGates, CampaignError, CampaignLimits, CollisionWitness, ComponentRef, ExactPose,
    GateOutcome, InputIdentity, ModelCoordinate, Prepared, TerminalVerdict,
};

trait TestValue<T> {
    fn test_value(self) -> T;
}

impl<T, E: std::fmt::Debug> TestValue<T> for Result<T, E> {
    fn test_value(self) -> T {
        match self {
            Ok(value) => value,
            Err(error) => panic!("test setup failed: {error:?}"),
        }
    }
}

impl<T> TestValue<T> for Option<T> {
    fn test_value(self) -> T {
        match self {
            Some(value) => value,
            None => panic!("test setup unexpectedly produced None"),
        }
    }
}

fn identity() -> InputIdentity {
    InputIdentity::new("board-sha", "rules-sha", "solver-build", "axis-x").test_value()
}

fn limits() -> CampaignLimits {
    CampaignLimits::new(4, 120_000).test_value()
}

fn pose(x: i64, y: i64, rotation: u8) -> ExactPose {
    ExactPose::new(
        ModelCoordinate::new(x).test_value(),
        ModelCoordinate::new(y).test_value(),
        RotationQuadrant::from_raw(rotation as i64),
    )
    .test_value()
}

fn prepared() -> Prepared {
    Prepared::new(identity(), vec!["U1", "R1"], limits()).test_value()
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
    assert!(CollisionWitness::new(
        "U1",
        "R1",
        temper_geometry::body_collision::AREA_TOLERANCE_MM2,
        "candidate",
    )
    .is_err());
    assert!(Prepared::new(identity(), vec!["U1", "U1"], limits()).is_err());
}

fn valid_refining_checkpoint_json() -> Value {
    let witness = CollisionWitness::new("U1", "R1", 0.25, "candidate").test_value();
    let decision = prepared()
        .start_solving()
        .test_value()
        .complete_candidate(vec![("U1", pose(100, 200, 0)), ("R1", pose(300, 400, 1))])
        .test_value()
        .audit(AuditGates::all_passed(), vec![witness])
        .test_value();
    let refining = match decision {
        temper_orchestration::collision_campaign::AuditDecision::Refining(refining) => refining,
        other => panic!("expected refinement, got {other:?}"),
    };
    let bytes = refining.checkpoint().to_bytes().test_value();
    serde_json::from_slice(&bytes[8..]).test_value()
}

fn checkpoint_bytes(payload: &Value) -> Vec<u8> {
    let mut bytes = b"TCAMP001".to_vec();
    bytes.extend(serde_json::to_vec(payload).test_value());
    bytes
}

#[test]
fn checkpoint_rejects_unvalidated_pose_and_noncanonical_pair() {
    let mut invalid_pose = valid_refining_checkpoint_json();
    invalid_pose["state"]["cuts"][0]["key"]["first_pose"]["rotation_index"] = json!(4);
    assert!(
        temper_orchestration::collision_campaign::CampaignCheckpoint::from_bytes(
            &checkpoint_bytes(&invalid_pose)
        )
        .is_err()
    );

    let mut self_pair = valid_refining_checkpoint_json();
    self_pair["state"]["cuts"][0]["key"]["pair"]["first"] = json!("U1");
    self_pair["state"]["cuts"][0]["key"]["pair"]["second"] = json!("U1");
    assert!(
        temper_orchestration::collision_campaign::CampaignCheckpoint::from_bytes(
            &checkpoint_bytes(&self_pair)
        )
        .is_err()
    );
}

#[test]
fn pairs_and_cut_keys_are_canonical_and_identity_bound() {
    let witness = CollisionWitness::new("R1", "U1", 0.25, "candidate-1").test_value();
    let first = prepared()
        .start_solving()
        .test_value()
        .complete_candidate(vec![("U1", pose(100, 200, 0)), ("R1", pose(300, 400, 1))])
        .test_value()
        .audit(AuditGates::all_passed(), vec![witness.clone()])
        .test_value();
    let cut = match first {
        temper_orchestration::collision_campaign::AuditDecision::Refining(refining) => {
            refining.cuts().first().test_value().clone()
        }
        other => panic!("expected refinement, got {other:?}"),
    };
    assert_eq!(cut.pair().first().as_str(), "R1");
    assert_eq!(cut.pair().second().as_str(), "U1");

    let reversed = prepared()
        .start_solving()
        .test_value()
        .complete_candidate(vec![("R1", pose(300, 400, 1)), ("U1", pose(100, 200, 0))])
        .test_value();
    let decision = reversed
        .audit(AuditGates::all_passed(), vec![witness])
        .test_value();
    let reversed_cut = match decision {
        temper_orchestration::collision_campaign::AuditDecision::Refining(refining) => {
            refining.cuts().first().test_value().clone()
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
        .test_value()
        .complete_candidate(vec![("U1", pose(100, 200, 0)), ("R1", pose(300, 400, 1))])
        .test_value();
    let decision = candidate
        .audit(AuditGates::all_passed(), vec![])
        .test_value();
    assert!(matches!(
        decision,
        temper_orchestration::collision_campaign::AuditDecision::Terminal(
            TerminalVerdict::Accepted { .. },
            _,
        )
    ));

    let candidate = prepared()
        .start_solving()
        .test_value()
        .complete_candidate(vec![("U1", pose(100, 200, 0)), ("R1", pose(300, 400, 1))])
        .test_value();
    let decision = candidate
        .audit(
            AuditGates::new(
                GateOutcome::Rejected("creepage shortfall".into()),
                GateOutcome::Passed,
                GateOutcome::Trusted,
            ),
            vec![],
        )
        .test_value();
    assert!(matches!(
        decision,
        temper_orchestration::collision_campaign::AuditDecision::Terminal(
            TerminalVerdict::VerifierRejected { .. },
            _,
        )
    ));

    let candidate = prepared()
        .start_solving()
        .test_value()
        .complete_candidate(vec![("U1", pose(100, 200, 0)), ("R1", pose(300, 400, 1))])
        .test_value();
    let witness = CollisionWitness::new("U1", "R1", 0.25, "candidate-1").test_value();
    let decision = candidate
        .audit(
            AuditGates::new(
                GateOutcome::Passed,
                GateOutcome::Rejected("body collision".into()),
                GateOutcome::Trusted,
            ),
            vec![witness],
        )
        .test_value();
    assert!(matches!(
        decision,
        temper_orchestration::collision_campaign::AuditDecision::Refining(_)
    ));
}

#[test]
fn collision_witness_cannot_override_failed_creepage_or_untrusted_provenance() {
    let witness = CollisionWitness::new("U1", "R1", 0.25, "candidate-1").test_value();
    let candidate = prepared()
        .start_solving()
        .test_value()
        .complete_candidate(vec![("U1", pose(100, 200, 0)), ("R1", pose(300, 400, 1))])
        .test_value();
    let decision = candidate
        .audit(
            AuditGates::new(
                GateOutcome::Rejected("creepage shortfall".into()),
                GateOutcome::Rejected("body collision".into()),
                GateOutcome::Trusted,
            ),
            vec![witness.clone()],
        )
        .test_value();
    assert!(matches!(
        decision,
        temper_orchestration::collision_campaign::AuditDecision::Terminal(
            TerminalVerdict::VerifierRejected { .. },
            _,
        )
    ));

    let candidate = prepared()
        .start_solving()
        .test_value()
        .complete_candidate(vec![("U1", pose(100, 200, 0)), ("R1", pose(300, 400, 1))])
        .test_value();
    let decision = candidate
        .audit(
            AuditGates::new(
                GateOutcome::Passed,
                GateOutcome::Rejected("body collision".into()),
                GateOutcome::Passed,
            ),
            vec![witness],
        )
        .test_value();
    assert!(matches!(
        decision,
        temper_orchestration::collision_campaign::AuditDecision::Terminal(
            TerminalVerdict::VerifierRejected { .. },
            _,
        )
    ));
}

#[test]
fn duplicate_frontier_is_no_progress_and_terminal_cannot_resume() {
    let solver = prepared().start_solving().test_value();
    let candidate = solver
        .complete_candidate(vec![("U1", pose(1, 2, 0)), ("R1", pose(3, 4, 0))])
        .test_value();
    let witness = CollisionWitness::new("U1", "R1", 1.0, "candidate").test_value();
    let refining = match candidate
        .audit(AuditGates::all_passed(), vec![witness.clone()])
        .test_value()
    {
        temper_orchestration::collision_campaign::AuditDecision::Refining(value) => value,
        other => panic!("expected refinement, got {other:?}"),
    };
    let candidate = refining
        .next_round()
        .test_value()
        .complete_candidate(vec![("U1", pose(1, 2, 0)), ("R1", pose(3, 4, 0))])
        .test_value();
    let terminal = match candidate
        .audit(AuditGates::all_passed(), vec![witness])
        .test_value()
    {
        temper_orchestration::collision_campaign::AuditDecision::Terminal(value, _) => value,
        other => panic!("expected terminal, got {other:?}"),
    };
    assert!(matches!(terminal, TerminalVerdict::NoProgress { .. }));
    assert!(terminal.resume().is_err());
}

#[test]
fn round_limit_terminal_checkpoint_retains_post_audit_collision_cut() {
    let campaign = Prepared::new(
        identity(),
        vec!["U1", "R1"],
        CampaignLimits::new(1, 120_000).test_value(),
    )
    .test_value();
    let witness = CollisionWitness::new("U1", "R1", 1.0, "candidate").test_value();
    let decision = campaign
        .start_solving()
        .test_value()
        .complete_candidate(vec![("U1", pose(100, 200, 0)), ("R1", pose(300, 400, 1))])
        .test_value()
        .audit(AuditGates::all_passed(), vec![witness])
        .test_value();
    let (verdict, checkpoint) = match decision {
        temper_orchestration::collision_campaign::AuditDecision::Terminal(verdict, checkpoint) => {
            (verdict, checkpoint)
        }
        other => panic!("expected round-limit terminal, got {other:?}"),
    };
    assert!(matches!(
        verdict,
        TerminalVerdict::BudgetExhausted { ref reason }
            if reason.contains("maximum campaign rounds reached (1)")
    ));

    let payload: Value =
        serde_json::from_slice(&checkpoint.to_bytes().test_value()[8..]).test_value();
    assert_eq!(payload["state"]["cuts"].as_array().test_value().len(), 1);
    assert!(payload["terminal"]["BudgetExhausted"]["reason"]
        .as_str()
        .test_value()
        .contains("maximum campaign rounds reached (1)"));
}

#[test]
fn solving_terminal_transitions_are_typed_and_reject_empty_reasons() {
    let unresolved = prepared()
        .start_solving()
        .test_value()
        .solver_unresolved("solver timeout")
        .test_value();
    assert!(matches!(
        unresolved,
        TerminalVerdict::SolverUnresolved { ref reason } if reason == "solver timeout"
    ));

    let infeasible = prepared()
        .start_solving()
        .test_value()
        .proven_infeasible("no feasible assignment")
        .test_value();
    assert!(matches!(
        infeasible,
        TerminalVerdict::ProvenInfeasible { ref reason } if reason == "no feasible assignment"
    ));

    let exhausted = prepared()
        .start_solving()
        .test_value()
        .budget_exhausted("campaign budget")
        .test_value();
    assert!(matches!(
        exhausted,
        TerminalVerdict::BudgetExhausted { ref reason } if reason == "campaign budget"
    ));

    assert!(prepared()
        .start_solving()
        .test_value()
        .solver_unresolved("  ")
        .is_err());
    assert!(prepared()
        .start_solving()
        .test_value()
        .proven_infeasible("")
        .is_err());
    assert!(prepared()
        .start_solving()
        .test_value()
        .budget_exhausted("")
        .is_err());
}

#[test]
fn checkpoints_are_versioned_and_reject_foreign_identity() {
    let checkpoint = prepared().checkpoint();
    let bytes = checkpoint.to_bytes().test_value();
    let restored = temper_orchestration::collision_campaign::CampaignCheckpoint::from_bytes(&bytes)
        .test_value();
    assert!(restored.validate_identity(&identity()).is_ok());
    assert!(restored.restore_for(&identity()).is_ok());
    let foreign =
        InputIdentity::new("other-board", "rules-sha", "solver-build", "axis-x").test_value();
    assert!(matches!(
        restored.validate_identity(&foreign),
        Err(CampaignError::ForeignIdentity { .. })
    ));
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
