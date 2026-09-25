#[path = "audit.rs"]
mod audit;

use std::io::Cursor;

fn headers() -> String {
    [
        "time", "v(acsrc)", "v(acn)", "i(Vac)", "v(load)", "v(vb)", "i(Lboost)",
        "v(vd)", "v(sw)", "v(gate)", "v(q)", "v(en)", "v(fault)", "v(vcomp)",
        "v(icomp)", "v(xu.raw)", "v(xu.pwm_hold)", "v(pwm)", "v(pwm_input)",
        "v(xdriver.driver_req)", "v(xdriver.drv_delay)", "v(xu.phase)", "v(xu.blank)",
        "v(isense)", "v(xu.ov)", "v(xu.fault)", "v(xu.pcl_hold)", "v(xu.pcl_request)",
        "v(disable)", "v(xu.m1)", "v(xu.m2)",
    ]
    .join(" ")
}

fn row(time: f64, vb: f64, il: f64, vd: f64, sw: f64, gate: f64, drv: f64) -> String {
    let mut values = [0.0; 31];
    values[0] = time;
    values[5] = vb;
    values[6] = il;
    values[7] = vd;
    values[8] = sw;
    values[9] = gate;
    values[20] = drv;
    values
        .iter()
        .map(|value| format!("{value:.17e}"))
        .collect::<Vec<_>>()
        .join(" ")
}

fn input(rows: &[String]) -> String {
    format!("{}\n{}\n", headers(), rows.join("\n"))
}

#[test]
fn tiny_energy_and_event_artifact_preserve_signed_pair() {
    let data = input(&[
        row(0.0, 10.0, 2.0, 20.0, 30.0, 4.0, 5.0),
        row(1.0, 10.0, 2.0, 20.0, 30.0, 4.0, 5.0),
        row(1.0, 12.0, 3.0, 21.0, 32.0, 5.0, 6.0),
        row(2.0, 12.0, 3.0, 21.0, 32.0, 5.0, 6.0),
    ]);
    let mut artifact = Vec::new();
    let summary = audit::analyze(Cursor::new(data), &mut artifact).expect("valid events");
    assert_eq!(summary.rows, 4);
    assert_eq!(summary.equal_groups, 1);
    assert_eq!(summary.equal_repeats, 1);
    let bank = &summary.energies[0];
    assert_eq!(bank.pairs, 1);
    assert!((bank.signed_sum_j - 0.5 * 2240e-6 * (12.0 - 10.0) * (12.0 + 10.0)).abs() < 1e-12);
    assert!(bank.absolute_sum_j > 0.0);
    let artifact_text = String::from_utf8(artifact).expect("artifact utf8");
    assert!(artifact_text.contains("LEFT\t1"));
    assert!(artifact_text.contains("GROUP\t1"));
    assert!(artifact_text.contains("RIGHT\t1"));
}

#[test]
fn identical_rows_have_zero_delta_and_group_rows_are_all_emitted() {
    let repeated = row(1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0);
    let data = input(&[row(0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0), repeated.clone(), repeated.clone(), repeated, row(2.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0)]);
    let mut artifact = Vec::new();
    let summary = audit::analyze(Cursor::new(data), &mut artifact).expect("identical group");
    assert_eq!(summary.equal_groups, 1);
    assert_eq!(summary.equal_repeats, 2);
    assert_eq!(summary.max_group_rows, 3);
    assert!(summary.deltas.iter().all(|delta| delta.max_abs == 0.0));
    let lines = String::from_utf8(artifact).unwrap().lines().count();
    assert_eq!(lines, 1 + 1 + 3 + 1);
}

#[test]
fn duplicate_peak_is_in_artifact_and_delta_summary() {
    let data = input(&[
        row(0.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0),
        row(1.0, 2.0, 2.0, 2.0, 2.0, 2.0, 2.0),
        row(1.0, 9.0, 9.0, 9.0, 9.0, 9.0, 9.0),
        row(2.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0),
    ]);
    let mut artifact = Vec::new();
    let summary = audit::analyze(Cursor::new(data), &mut artifact).expect("duplicate peak");
    assert_eq!(summary.deltas[5].max_abs, 7.0);
    assert!(summary.deltas[5].max_normalized > 1.0);
    assert!(String::from_utf8(artifact).unwrap().contains("9.000000"));
}

#[test]
fn backward_time_and_nonfinite_values_are_rejected() {
    let backward = input(&[row(1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0), row(0.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0)]);
    let mut artifact = Vec::new();
    assert!(audit::analyze(Cursor::new(backward), &mut artifact).unwrap_err().0.contains("backward"));
    let mut bad = row(0.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0)
        .split_whitespace()
        .map(str::to_string)
        .collect::<Vec<_>>();
    bad[5] = "NaN".to_string();
    let bad = format!("{}\n{}\n", headers(), bad.join(" "));
    assert!(audit::analyze(Cursor::new(bad), &mut artifact).unwrap_err().0.contains("non-finite"));
}

#[test]
fn signed_round_trip_has_zero_net_but_nonzero_absolute_energy() {
    // Two equal-time transitions, first +2 V and then -2 V.  The signed
    // telescoping sum is zero while the absolute disturbance is retained.
    let data = input(&[
        row(0.0, 10.0, 0.0, 0.0, 0.0, 0.0, 0.0),
        row(1.0, 10.0, 0.0, 0.0, 0.0, 0.0, 0.0),
        row(1.0, 12.0, 0.0, 0.0, 0.0, 0.0, 0.0),
        row(2.0, 12.0, 0.0, 0.0, 0.0, 0.0, 0.0),
        row(3.0, 12.0, 0.0, 0.0, 0.0, 0.0, 0.0),
        row(3.0, 10.0, 0.0, 0.0, 0.0, 0.0, 0.0),
        row(4.0, 10.0, 0.0, 0.0, 0.0, 0.0, 0.0),
    ]);
    let mut artifact = Vec::new();
    let summary = audit::analyze(Cursor::new(data), &mut artifact).expect("round trip");
    let bank = &summary.energies[0];
    assert_eq!(bank.pairs, 2);
    assert!(bank.signed_sum_j.abs() < 1e-15);
    assert!(bank.absolute_sum_j > 0.0);
}

#[test]
fn differential_gate_sw_energy_ignores_common_mode() {
    let data = input(&[
        row(0.0, 0.0, 0.0, 0.0, 10.0, 2.0, 0.0),
        row(1.0, 0.0, 0.0, 0.0, 10.0, 2.0, 0.0),
        row(1.0, 0.0, 0.0, 0.0, 11.0, 3.0, 0.0),
        row(2.0, 0.0, 0.0, 0.0, 11.0, 3.0, 0.0),
    ]);
    let mut artifact = Vec::new();
    let summary = audit::analyze(Cursor::new(data), &mut artifact).expect("common mode");
    assert_eq!(summary.energies[4].pairs, 1);
    assert_eq!(summary.energies[4].signed_sum_j, 0.0);
    assert_eq!(summary.energies[4].absolute_sum_j, 0.0);
    assert!(summary.energies[5].absolute_sum_j > 0.0);
}

#[test]
fn adjacent_groups_keep_left_and_right_context() {
    let data = input(&[
        row(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
        row(1.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0),
        row(1.0, 2.0, 0.0, 0.0, 0.0, 0.0, 0.0),
        row(2.0, 3.0, 0.0, 0.0, 0.0, 0.0, 0.0),
        row(2.0, 4.0, 0.0, 0.0, 0.0, 0.0, 0.0),
        row(3.0, 5.0, 0.0, 0.0, 0.0, 0.0, 0.0),
    ]);
    let mut artifact = Vec::new();
    let summary = audit::analyze(Cursor::new(data), &mut artifact).expect("adjacent groups");
    assert_eq!(summary.equal_groups, 2);
    assert_eq!(summary.right_context_missing, 0);
    let text = String::from_utf8(artifact).unwrap();
    assert!(text.contains("LEFT\t1\t1\t"));
    assert!(text.contains("RIGHT\t1\t4\t"));
    assert!(text.contains("LEFT\t2\t3\t"));
    assert!(text.contains("RIGHT\t2\t6\t"));
}

#[test]
fn eof_group_is_reported_without_fabricated_right_context() {
    let data = input(&[
        row(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
        row(1.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0),
        row(1.0, 2.0, 0.0, 0.0, 0.0, 0.0, 0.0),
    ]);
    let mut artifact = Vec::new();
    let summary = audit::analyze(Cursor::new(data), &mut artifact).expect("eof duplicate");
    assert_eq!(summary.right_context_missing, 1);
    assert!(!String::from_utf8(artifact).unwrap().contains("RIGHT\t1\t"));
}

#[test]
fn malformed_header_is_rejected_before_rows() {
    let mut duplicate = headers().split_whitespace().map(str::to_string).collect::<Vec<_>>();
    duplicate[1] = duplicate[0].clone();
    let duplicate = format!("{}\n{}\n", duplicate.join(" "), row(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0));
    let mut artifact = Vec::new();
    assert!(audit::analyze(Cursor::new(duplicate), &mut artifact).unwrap_err().0.contains("unique"));

    let missing = headers().split_whitespace().take(30).collect::<Vec<_>>().join(" ");
    let missing = format!("{missing}\n{}\n", row(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0));
    assert!(audit::analyze(Cursor::new(missing), &mut artifact).is_err());
}
