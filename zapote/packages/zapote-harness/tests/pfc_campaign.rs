//! G0 acceptance tests for the bounded campaign adapter.
//!
//! These are the checks the plan requires before numeric fan-out: baseline
//! parity, a bounded matched-power solve with explicit derating, a model-domain
//! boundary that returns UNSUPPORTED instead of a fabricated number, and a
//! strict case census. They reuse the maintained kernels only.

use zapote_harness::pfc_campaign::{
    run_case, run_manifest, CaseInput, CaseStatus, DeviceInput, DriveInput, SCHEMA_MANIFEST,
};

/// Retained baseline: IPW65R045C7 / UCC27624 / 12 V / 4.7 ohm external, no-assist.
fn baseline_device() -> DeviceInput {
    DeviceInput {
        id: "IPW65R045C7".into(),
        qg_c: 93e-9,
        qgd_c: 30e-9,
        plateau_v: 5.4,
        intrinsic_gate_r_ohm: 0.85,
        eoss_j: 11.7e-6,
        rds_on_ohm: 0.045,
    }
}

fn baseline_drive() -> DriveInput {
    DriveInput {
        gate_bias_v: 12.0,
        // no-assist profile: source 5.0 ohm, sink 0.6 ohm, in series with 4.7 ohm.
        external_gate_r_on_ohm: 4.7 + 5.0,
        external_gate_r_off_ohm: 4.7 + 0.6,
        driver_source_peak_a: 5.0,
        driver_sink_peak_a: 5.0,
        current_transfer_charge_c: 10e-9,
        loop_inductance_h: 10e-9,
        timestep_s: 0.25e-9,
    }
}

fn baseline_frequency_hz() -> f64 {
    zapote_erc::power_entry::frequency_from_rf(16_200.0).unwrap()
}

fn case(id: &str, line_v: f64, l_h: f64, f_hz: f64, power_w: f64) -> CaseInput {
    CaseInput {
        case_id: id.into(),
        line_rms_v: line_v,
        bus_v: 400.0,
        inductance_h: l_h,
        switching_hz: f_hz,
        requested_power_w: power_w,
        input_rms_ceiling_a: 15.0,
    }
}

#[test]
fn baseline_case_reproduces_the_retained_control() {
    let c = case("control-120v", 120.0, 180e-6, baseline_frequency_hz(), 1796.31003212911);
    let r = run_case(&c, &baseline_device(), &baseline_drive()).unwrap();
    assert_eq!(r.status, CaseStatus::Solved);
    let m = r.moments.as_ref().unwrap();
    assert!(
        (m.input_power_w - 1796.31003212911).abs() < 1e-6,
        "achieved input power {}",
        m.input_power_w
    );
    let total = r.total_switch_gate_w.unwrap();
    assert!(
        (total - 45.502337474982966).abs() < 1e-6,
        "baseline partial switch/gate loss {total} does not match the retained control"
    );
}

#[test]
fn requirement_exactly_at_the_ceiling_is_not_reported_as_derated() {
    // The retained control is defined at 15 A true RMS, so the matched-power
    // solve must land exactly on the ceiling without flagging a derating.
    let c = case("control-ceiling", 120.0, 180e-6, baseline_frequency_hz(), 1796.31003212911);
    let r = run_case(&c, &baseline_device(), &baseline_drive()).unwrap();
    assert!(!r.ceiling_binds);
    assert!((r.required_input_rms_a.unwrap() - 15.0).abs() < 1e-9);
    assert!(r.power_shortfall_w.unwrap().abs() < 1e-9);
}

#[test]
fn low_line_derates_instead_of_absorbing_the_shortfall() {
    let c = case("low-line", 108.0, 180e-6, baseline_frequency_hz(), 1796.31003212911);
    let r = run_case(&c, &baseline_device(), &baseline_drive()).unwrap();
    assert_eq!(r.status, CaseStatus::Derated);
    assert!(r.ceiling_binds);
    assert!(r.required_input_rms_a.unwrap() > 16.0);
    let achieved = r.achieved_input_power_w.unwrap();
    assert!(
        (1600.0..1640.0).contains(&achieved),
        "achieved {achieved} W at 108 V should be the ceiling-limited power, not the request"
    );
    assert!(r.power_shortfall_w.unwrap() > 150.0);
}

#[test]
fn a_domain_boundary_is_unsupported_not_a_zero_loss_case() {
    // At 120 V / 180 uH / 129 kHz the current model's DCM guard fires below a
    // few hundred watts. That is a model-domain gap: it must not be reported
    // as a solved low-loss point.
    let c = case("low-load-dcm", 120.0, 180e-6, baseline_frequency_hz(), 100.0);
    let r = run_case(&c, &baseline_device(), &baseline_drive()).unwrap();
    assert_eq!(r.status, CaseStatus::Unsupported);
    assert!(r.total_switch_gate_w.is_none());
    assert!(r.losses.is_none());
    assert!(r.unsupported_reason.is_some());
}

#[test]
fn fixed_lf_product_is_invariant_with_a_monotone_total() {
    // Regression for the measured degeneracy: at fixed L*f the current moments
    // are invariant and only f-proportional terms move, so the total is
    // strictly increasing in f. A future change that silently made the
    // frequency axis informative (or noisy) would break this.
    let f0 = baseline_frequency_hz();
    let l0 = 180e-6;
    let mut rows = Vec::new();
    for f in [30_000.0, 65_000.0, 129_107.391_985_769_05, 180_000.0] {
        let c = case(&format!("lf-{f}"), 120.0, l0 * f0 / f, f, 1796.31003212911);
        rows.push(run_case(&c, &baseline_device(), &baseline_drive()).unwrap());
    }
    let first = rows[0].moments.as_ref().unwrap();
    for r in &rows[1..] {
        let m = r.moments.as_ref().unwrap();
        assert!((m.input_power_w - first.input_power_w).abs() < 1e-6);
        assert!((m.switch_rms_a - first.switch_rms_a).abs() < 1e-9);
    }
    for pair in rows.windows(2) {
        let a = pair[0].total_switch_gate_w.unwrap();
        let b = pair[1].total_switch_gate_w.unwrap();
        assert!(b > a, "total loss is not strictly increasing in f at fixed L*f: {a} -> {b}");
    }
}

#[test]
fn explicit_inductance_actually_reaches_the_switch_moment() {
    // A guard against the parameterization silently reverting to the nominal
    // inductance: two cases differing only in L must produce different
    // switching currents (the DCM-free regime, so both solve).
    let f = baseline_frequency_hz();
    let a = run_case(&case("l-180", 120.0, 180e-6, f, 1796.31003212911), &baseline_device(), &baseline_drive()).unwrap();
    let b = run_case(&case("l-300", 120.0, 300e-6, f, 1796.31003212911), &baseline_device(), &baseline_drive()).unwrap();
    let ta = a.moments.as_ref().unwrap().mean_turn_on_a;
    let tb = b.moments.as_ref().unwrap().mean_turn_on_a;
    assert!((ta - tb).abs() > 1e-6, "inductance did not reach the waveform: {ta} vs {tb}");
}

#[test]
fn inductor_envelope_is_reported_and_shrinks_with_inductance() {
    let f = baseline_frequency_hz();
    let a = run_case(&case("env-180", 120.0, 180e-6, f, 1796.31003212911), &baseline_device(), &baseline_drive()).unwrap();
    let b = run_case(&case("env-360", 120.0, 360e-6, f, 1796.31003212911), &baseline_device(), &baseline_drive()).unwrap();
    let ma = a.moments.as_ref().unwrap();
    let mb = b.moments.as_ref().unwrap();
    assert!(ma.inductor_peak_a.is_finite() && ma.inductor_peak_a > 0.0);
    assert!(
        mb.ripple_peak_to_peak_max_a < ma.ripple_peak_to_peak_max_a,
        "ripple did not shrink with more inductance"
    );
    assert!(mb.inductor_peak_a < ma.inductor_peak_a);
}

fn manifest_json(cases: &str, schema: &str) -> Vec<u8> {
    format!(
        r#"{{"schema":"{schema}","device":{{"id":"IPW65R045C7","qg_c":0.000000093,"qgd_c":0.00000003,"plateau_v":5.4,"intrinsic_gate_r_ohm":0.85,"eoss_j":0.0000117,"rds_on_ohm":0.045}},"drive":{{"gate_bias_v":12.0,"external_gate_r_on_ohm":9.7,"external_gate_r_off_ohm":5.3,"driver_source_peak_a":5.0,"driver_sink_peak_a":5.0,"current_transfer_charge_c":0.00000001,"loop_inductance_h":0.00000001,"timestep_s":0.00000000025}},"cases":[{cases}]}}"#
    )
    .into_bytes()
}

#[test]
fn manifest_census_yields_exactly_one_result_per_declared_case() {
    let cases = r#"{"case_id":"a","line_rms_v":120,"bus_v":400,"inductance_h":0.00018,"switching_hz":129107.39198576905,"requested_power_w":1796.31003212911,"input_rms_ceiling_a":15},
                   {"case_id":"b","line_rms_v":108,"bus_v":400,"inductance_h":0.00018,"switching_hz":129107.39198576905,"requested_power_w":1796.31003212911,"input_rms_ceiling_a":15},
                   {"case_id":"c","line_rms_v":120,"bus_v":400,"inductance_h":0.00018,"switching_hz":129107.39198576905,"requested_power_w":100,"input_rms_ceiling_a":15}"#;
    let report = run_manifest(&manifest_json(cases, SCHEMA_MANIFEST)).unwrap();
    assert_eq!(report.census.expected, 3);
    assert_eq!(report.census.solved, 1);
    assert_eq!(report.census.derated, 1);
    assert_eq!(report.census.unsupported, 1);
    assert_eq!(report.cases.len(), 3);
    assert_eq!(report.cases[0].case_id, "a");
    assert_eq!(report.cases[2].status, CaseStatus::Unsupported);
}

#[test]
fn duplicate_case_ids_are_rejected() {
    let cases = r#"{"case_id":"dup","line_rms_v":120,"bus_v":400,"inductance_h":0.00018,"switching_hz":129107.39198576905,"requested_power_w":1796.31003212911,"input_rms_ceiling_a":15},
                   {"case_id":"dup","line_rms_v":132,"bus_v":400,"inductance_h":0.00018,"switching_hz":129107.39198576905,"requested_power_w":1796.31003212911,"input_rms_ceiling_a":15}"#;
    let err = run_manifest(&manifest_json(cases, SCHEMA_MANIFEST)).unwrap_err();
    assert!(err.contains("duplicate case_id"), "{err}");
}

#[test]
fn unknown_schema_and_unknown_fields_are_rejected() {
    let cases = r#"{"case_id":"a","line_rms_v":120,"bus_v":400,"inductance_h":0.00018,"switching_hz":129107.39198576905,"requested_power_w":1796.31003212911,"input_rms_ceiling_a":15}"#;
    assert!(run_manifest(&manifest_json(cases, "zapote.pfc.campaign-manifest.v2")).is_err());
    let with_extra = r#"{"case_id":"a","line_rms_v":120,"bus_v":400,"inductance_h":0.00018,"switching_hz":129107.39198576905,"requested_power_w":1796.31003212911,"input_rms_ceiling_a":15,"surprise":1}"#;
    assert!(run_manifest(&manifest_json(with_extra, SCHEMA_MANIFEST)).is_err());
}

#[test]
fn non_physical_and_non_finite_inputs_are_rejected() {
    for bad in [
        case("neg", -120.0, 180e-6, baseline_frequency_hz(), 1796.31),
        case("zero-l", 120.0, 0.0, baseline_frequency_hz(), 1796.31),
        case("nan", 120.0, 180e-6, f64::NAN, 1796.31),
        case("inf", 120.0, 180e-6, baseline_frequency_hz(), f64::INFINITY),
    ] {
        assert!(
            run_case(&bad, &baseline_device(), &baseline_drive()).is_err(),
            "case {} should be rejected as INVALID_INPUT",
            bad.case_id
        );
    }
}
