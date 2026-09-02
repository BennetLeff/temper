use temper_quality_oracle::ct07_t2_qualification::{
    compute_u9_environment, EvidenceStatus, U9ControlChallengeRecord, U9EnvironmentalProtocol,
    U9EnvironmentRecord, U9ReplayInput, U9_REQUIRED_AXES,
};

fn protocol() -> U9EnvironmentalProtocol {
    serde_json::from_str(include_str!(
        "../../../power_pcb_dataset/qualification/ct07_t2/mechanical_protocol.json"
    ))
    .expect("mechanical protocol fixture must be valid")
}

#[test]
fn no_samples_or_controls_stays_pending_without_fabricated_results() {
    let protocol = protocol();
    let result = compute_u9_environment(&U9ReplayInput {
        protocol,
        records: vec![],
        control_challenges: vec![],
        u5_protocol: None,
    })
    .expect("pending placeholder is a valid replay input");

    assert_eq!(result.status, EvidenceStatus::Pending);
    assert_eq!(result.record_count, 0);
    assert!(result
        .reasons
        .iter()
        .any(|reason| reason.contains("no U9 stress records")));
}

#[test]
fn a_record_without_every_checkpoint_and_axis_stays_pending() {
    let mut protocol = protocol();
    protocol.construction_digest = "a".repeat(64);
    let record = U9EnvironmentRecord {
        schema_version: 1,
        record_id: "post-vibration-a0".to_owned(),
        record_type: "geometry".to_owned(),
        checkpoint_id: "post-vibration".to_owned(),
        construction_id: protocol.construction_id.clone(),
        construction_digest: protocol.construction_digest.clone(),
        protocol_digest: protocol.protocol_digest.clone(),
        lot_id: "lot-a".to_owned(),
        sample_id: "sample-a0".to_owned(),
        assembly_index: 0,
        status: EvidenceStatus::Pass,
        axes: vec![],
        evidence_ids: vec![],
        repaired: false,
        replaced: false,
        process_changed: false,
        electrical_capture: None,
    };
    let result = compute_u9_environment(&U9ReplayInput {
        protocol,
        records: vec![record],
        control_challenges: vec![],
        u5_protocol: None,
    })
    .expect("incomplete evidence is pending, not fabricated");

    assert_eq!(result.status, EvidenceStatus::Pending);
    assert!(result.reasons.iter().any(|reason| reason.contains("checkpoint")));
}

#[test]
fn repair_replacement_or_process_change_is_rejected() {
    let mut protocol = protocol();
    protocol.construction_digest = "b".repeat(64);
    let record = U9EnvironmentRecord {
        schema_version: 1,
        record_id: "post-stress-repaired".to_owned(),
        record_type: "structural".to_owned(),
        checkpoint_id: "post-stress-final".to_owned(),
        construction_id: protocol.construction_id.clone(),
        construction_digest: protocol.construction_digest.clone(),
        protocol_digest: protocol.protocol_digest.clone(),
        lot_id: "lot-a".to_owned(),
        sample_id: "sample-a0".to_owned(),
        assembly_index: 0,
        status: EvidenceStatus::Pass,
        axes: vec![],
        evidence_ids: vec![],
        repaired: true,
        replaced: false,
        process_changed: false,
        electrical_capture: None,
    };

    let error = compute_u9_environment(&U9ReplayInput {
        protocol,
        records: vec![record],
        control_challenges: vec![],
        u5_protocol: None,
    })
    .expect_err("repaired samples cannot reuse pre-stress qualification");
    assert!(error.to_string().contains("repair"));
}

#[test]
fn control_record_must_bind_to_same_construction() {
    let mut protocol = protocol();
    protocol.construction_digest = "c".repeat(64);
    let control = U9ControlChallengeRecord {
        schema_version: 1,
        challenge_id: "wrong-ct-variant".to_owned(),
        construction_id: protocol.construction_id.clone(),
        construction_digest: "d".repeat(64),
        lot_id: "lot-a".to_owned(),
        sample_id: "sample-a0".to_owned(),
        observed_outcome: "rejected".to_owned(),
        status: EvidenceStatus::Pass,
        evidence_ids: vec!["control-photo-1".to_owned()],
    };

    let error = compute_u9_environment(&U9ReplayInput {
        protocol,
        records: vec![],
        control_challenges: vec![control],
        u5_protocol: None,
    })
    .expect_err("control evidence cannot cross construction identities");
    assert!(error.to_string().contains("construction identity"));
}

#[test]
fn only_an_explicit_complete_synthetic_matrix_can_pass() {
    let mut protocol = protocol();
    protocol.construction_digest = "e".repeat(64);
    protocol.protocol_digest = "f".repeat(64);
    let mut records = Vec::new();
    for assembly_index in 0..protocol.sample_floor.complete_assemblies {
        let lot_id = if assembly_index < 3 { "lot-a" } else { "lot-b" };
        let sample_id = format!("sample-{assembly_index}");
        for checkpoint in &protocol.checkpoints {
            records.push(U9EnvironmentRecord {
                schema_version: 1,
                record_id: format!("{}-{assembly_index}", checkpoint.id),
                record_type: "post-stress".to_owned(),
                checkpoint_id: checkpoint.id.clone(),
                construction_id: protocol.construction_id.clone(),
                construction_digest: protocol.construction_digest.clone(),
                protocol_digest: protocol.protocol_digest.clone(),
                lot_id: lot_id.to_owned(),
                sample_id: sample_id.clone(),
                assembly_index,
                status: EvidenceStatus::Pass,
                axes: U9_REQUIRED_AXES
                    .iter()
                    .map(|code| temper_quality_oracle::ct07_t2_qualification::U9AxisObservation {
                        code: (*code).to_owned(),
                        status: EvidenceStatus::Pass,
                        reason: "synthetic test observation".to_owned(),
                        evidence_ids: vec!["synthetic".to_owned()],
                    })
                    .collect(),
                evidence_ids: vec!["synthetic".to_owned()],
                repaired: false,
                replaced: false,
                process_changed: false,
                electrical_capture: None,
            });
        }
    }
    let controls = protocol
        .control_challenges
        .iter()
        .map(|challenge| U9ControlChallengeRecord {
            schema_version: 1,
            challenge_id: challenge.id.clone(),
            construction_id: protocol.construction_id.clone(),
            construction_digest: protocol.construction_digest.clone(),
            lot_id: "lot-a".to_owned(),
            sample_id: "sample-0".to_owned(),
            observed_outcome: "reject".to_owned(),
            status: EvidenceStatus::Pass,
            evidence_ids: vec!["synthetic".to_owned()],
        })
        .collect();
    let result = compute_u9_environment(&U9ReplayInput {
        protocol,
        records,
        control_challenges: controls,
        u5_protocol: None,
    })
    .expect("complete synthetic matrix is valid input");

    assert_eq!(result.status, EvidenceStatus::Pass);
    assert_eq!(result.record_count, 30);
    assert_eq!(result.control_record_count, 8);
}
