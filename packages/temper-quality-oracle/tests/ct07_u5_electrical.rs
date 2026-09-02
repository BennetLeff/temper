use temper_quality_oracle::ct07_t2_qualification::{
    checked_nanoseconds, compute_u5_electrical, derive_capture, EvidenceStatus, RawCapture,
    ThresholdCrossingPolicy, U5ElectricalCapture, U5ElectricalProtocol, U5WaveformSample,
};

fn protocol() -> U5ElectricalProtocol {
    U5ElectricalProtocol {
        schema_version: 1,
        protocol_id: "u5-protocol".to_owned(),
        construction_id: "u6-construction".to_owned(),
        construction_digest: "d".repeat(64),
        protocol_digest: "a".repeat(64),
        threshold_policy: ThresholdCrossingPolicy {
            threshold_a: "60".to_owned(),
            direction: temper_quality_oracle::ct07_t2_qualification::FaultDirection::Rising,
            precondition_samples: 1,
            persistence_samples: 1,
        },
        trip_uncertainty_a: "0".to_owned(),
        ocp01_conservative_high_a: "50".to_owned(),
        ordering_uncertainty_a: "0".to_owned(),
        minimum_bandwidth_hz: 1,
        minimum_sample_rate_hz: 1,
        required_assemblies: 5,
        required_lots: 2,
        required_repetitions: 3,
        required_corners: vec!["corner-a".to_owned()],
        aggregate_timing_owner: "isolation-joint-r24-r25-v1".to_owned(),
        status: "pending".to_owned(),
    }
}

fn capture(
    p: &U5ElectricalProtocol,
    assembly: usize,
    repetition: usize,
    lot: &str,
) -> U5ElectricalCapture {
    U5ElectricalCapture {
        schema_version: 1,
        capture_id: format!("cap-{assembly}-{repetition}-{lot}"),
        construction_id: p.construction_id.clone(),
        construction_digest: p.construction_digest.clone(),
        protocol_digest: p.protocol_digest.clone(),
        lot_id: lot.to_owned(),
        sample_id: format!("sample-{assembly}"),
        assembly_index: assembly,
        repetition,
        corner: "corner-a".to_owned(),
        calibration_id: "cal-1".to_owned(),
        bandwidth_hz: 1,
        sample_rate_hz: 1,
        timestamp_uncertainty_ns: "0.25".to_owned(),
        trip_current_a: "60".to_owned(),
        clipped: false,
        samples: vec![
            U5WaveformSample {
                timestamp_ns: 0,
                primary_current_a: "40".to_owned(),
                comparator_asserted: false,
                latch_asserted: false,
            },
            U5WaveformSample {
                timestamp_ns: 10,
                primary_current_a: "60".to_owned(),
                comparator_asserted: true,
                latch_asserted: true,
            },
        ],
    }
}

#[test]
fn no_u6_samples_stays_pending_without_a_timing_bound() {
    let p = protocol();
    let result = compute_u5_electrical(&p, &[]).expect("protocol is valid");
    assert_eq!(result.status, EvidenceStatus::Pending);
    assert_eq!(result.valid_capture_count, 0);
    assert_eq!(
        result.sensor_threshold_to_system_latch_assertion_max_ns,
        None
    );
    assert!(result.reasons.iter().any(|r| r.contains("U6")));
}

#[test]
fn committed_u5_protocol_replays_as_pending_until_u6_freezes_identity() {
    let protocol: U5ElectricalProtocol = serde_json::from_str(include_str!(
        "../../../power_pcb_dataset/qualification/ct07_t2/electrical_protocol.json"
    ))
    .expect("committed electrical protocol matches the Rust schema");
    let result = compute_u5_electrical(&protocol, &[]).expect("pending protocol replays");
    assert_eq!(result.status, EvidenceStatus::Pending);
    assert_eq!(result.construction_digest, "pending-u6-freeze");
    assert!(result
        .sensor_threshold_to_system_latch_assertion_max_ns
        .is_none());
}

#[test]
fn complete_corner_matrix_derives_integer_ns_bound_but_keeps_u7_axes_pending() {
    let p = protocol();
    let mut captures = Vec::new();
    for assembly in 0..5 {
        for repetition in 1..=3 {
            captures.push(capture(
                &p,
                assembly,
                repetition,
                if assembly < 3 { "lot-a" } else { "lot-b" },
            ));
        }
    }
    let result = compute_u5_electrical(&p, &captures).expect("captures replay");
    assert_eq!(result.status, EvidenceStatus::Pending);
    assert_eq!(result.valid_capture_count, 15);
    assert_eq!(
        result.sensor_threshold_to_system_latch_assertion_max_ns,
        Some(1)
    );
    assert_eq!(
        result
            .axes
            .iter()
            .find(|axis| axis.code == "r3.trip-window-latency")
            .unwrap()
            .status,
        EvidenceStatus::Pass
    );
    assert_eq!(
        result
            .axes
            .iter()
            .find(|axis| axis.code == "r4.trip-ordering")
            .unwrap()
            .status,
        EvidenceStatus::Pass
    );
    assert_eq!(
        result
            .axes
            .iter()
            .find(|axis| axis.code == "r2.independent-coverage")
            .unwrap()
            .status,
        EvidenceStatus::Pending
    );
}

#[test]
fn clipped_and_construction_mismatch_captures_reject() {
    let p = protocol();
    let mut clipped = capture(&p, 0, 1, "lot-a");
    clipped.clipped = true;
    let result = compute_u5_electrical(&p, &[clipped]).expect("invalid capture is a result");
    assert_eq!(result.status, EvidenceStatus::Fail);
    assert_eq!(result.invalid_capture_count, 1);

    let mut mismatched = capture(&p, 0, 1, "lot-a");
    mismatched.construction_digest = "e".repeat(64);
    let result = compute_u5_electrical(&p, &[mismatched]).expect("invalid identity is a result");
    assert_eq!(result.status, EvidenceStatus::Fail);
    assert!(result
        .reasons
        .iter()
        .any(|r| r.contains("construction identity")));
}

#[test]
fn checked_nanoseconds_is_exact_decimal_and_rejects_noncanonical_or_overflowing_values() {
    assert_eq!(checked_nanoseconds("1.0001").unwrap(), 2);
    assert!(checked_nanoseconds("01").is_err());
    assert!(checked_nanoseconds(" 1").is_err());
    assert!(checked_nanoseconds("1e3").is_err());
    assert!(checked_nanoseconds("-1").is_err());
    assert!(checked_nanoseconds("170141183460469231731687303715884105727").is_err());
}

#[test]
fn committed_threshold_fixture_corpus_replays_with_the_normative_crossing_rule() {
    #[derive(serde::Deserialize)]
    struct Fixture {
        policy: ThresholdCrossingPolicy,
        capture: RawCapture,
    }
    let fixtures = [
        (
            "monotonic.json",
            include_str!("../testdata/ct07_t2_threshold_crossings/monotonic.json"),
            15,
        ),
        (
            "exact-equality.json",
            include_str!("../testdata/ct07_t2_threshold_crossings/exact-equality.json"),
            10,
        ),
        (
            "multi-crossing.json",
            include_str!("../testdata/ct07_t2_threshold_crossings/multi-crossing.json"),
            8,
        ),
        (
            "ringing.json",
            include_str!("../testdata/ct07_t2_threshold_crossings/ringing.json"),
            30,
        ),
    ];
    for (name, raw, crossing_ns) in fixtures {
        let fixture: Fixture = serde_json::from_str(raw).expect("fixture parses");
        let derived = derive_capture(&fixture.capture, &fixture.policy).expect("fixture replays");
        assert_eq!(derived.crossing_timestamp_ns, crossing_ns, "{name}");
    }
}
