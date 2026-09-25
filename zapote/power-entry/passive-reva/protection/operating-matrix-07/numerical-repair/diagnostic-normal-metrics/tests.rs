#[path = "metrics.rs"]
mod metrics;

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

fn row(time: f64, vb: f64, il: f64, vd: f64, sw: f64, gate: f64) -> String {
    let mut values = [0.0; 31];
    values[0] = time;
    values[5] = vb;
    values[6] = il;
    values[7] = vd;
    values[8] = sw;
    values[9] = gate;
    values
        .iter()
        .map(|value| format!("{value:.17e}"))
        .collect::<Vec<_>>()
        .join(" ")
}

fn trace(rows: &[String]) -> String {
    format!("{}\n{}\n", headers(), rows.join("\n"))
}

fn boundaries() -> [f64; 4] {
    [0.6, 37.0 / 60.0, 19.0 / 30.0, 0.65]
}

#[test]
fn linear_ramp_has_known_cycle_means_and_exact_boundaries() {
    let b = boundaries();
    let input = trace(&[
        row(0.0, 0.0, 1.0, 2.0, 3.0, -4.0),
        row(b[0], 10.0, 2.0, 3.0, 4.0, 5.0),
        row(b[1], 20.0, 3.0, 4.0, 5.0, 6.0),
        row(b[2], 30.0, 4.0, 5.0, 6.0, 7.0),
        row(b[3], 40.0, 5.0, 6.0, 7.0, 8.0),
    ]);
    let report = metrics::analyze(Cursor::new(input)).expect("complete ramp");
    assert_eq!(report.cycles.len(), 3);
    assert!((report.cycles[0].mean_vb - 15.0).abs() < 1e-12);
    assert!((report.cycles[1].mean_vb - 25.0).abs() < 1e-12);
    assert!((report.cycles[2].mean_vb - 35.0).abs() < 1e-12);
    assert_eq!(report.max_positive_gap, 0.6);
    assert_eq!(report.first_time, 0.0);
    assert_eq!(report.last_time, 0.65);
    assert!((report.cycle_mean_range_over_first_mean.unwrap() - (20.0 / 15.0)).abs() < 1e-12);
}

#[test]
fn duplicate_peak_is_retained_but_has_zero_duration() {
    let b = boundaries();
    let input = trace(&[
        row(0.0, 0.0, 1.0, 2.0, 3.0, 4.0),
        row(b[0], 10.0, 2.0, 3.0, 4.0, 5.0),
        row(b[1] - 0.001, 20.0, 3.0, 4.0, 5.0, 6.0),
        row(b[1] - 0.001, 99.0, 300.0, 400.0, 500.0, -600.0),
        row(b[1] - 0.001, 20.0, 3.0, 4.0, 5.0, 6.0),
        row(b[2], 30.0, 4.0, 5.0, 6.0, 7.0),
        row(b[3], 40.0, 5.0, 6.0, 7.0, 8.0),
    ]);
    let report = metrics::analyze(Cursor::new(input)).expect("duplicate trace");
    assert_eq!(report.duplicate_groups, 1);
    assert_eq!(report.duplicate_rows, 2);
    assert_eq!(report.vb.max, 99.0);
    assert_eq!(report.il.max, 300.0);
    assert_eq!(report.vds_sw_ground.max, 500.0);
    assert_eq!(report.abs_gate.max, 600.0);
    // The internal duplicate has zero duration and therefore does not alter
    // the trapezoid mean, while its peak remains in the cycle extrema.
    assert_eq!(report.cycles[0].max_vb, 99.0);
    let cycle_one_start = 20.0
        + (b[1] - (b[1] - 0.001)) * (30.0 - 20.0) / (b[2] - (b[1] - 0.001));
    assert!((report.cycles[1].mean_vb - (cycle_one_start + 30.0) / 2.0).abs() < 1e-12);
}

#[test]
fn one_positive_segment_can_span_all_three_cycles() {
    let b = boundaries();
    let input = trace(&[
        row(0.0, 0.0, 1.0, 2.0, 3.0, 4.0),
        row(0.65, 65.0, 2.0, 3.0, 4.0, 5.0),
    ]);
    let report = metrics::analyze(Cursor::new(input)).expect("single spanning segment");
    assert!((report.cycles[0].mean_vb - (100.0 * b[0] + 100.0 * b[1]) / 2.0).abs() < 1e-12);
    assert!((report.cycles[1].mean_vb - (100.0 * b[1] + 100.0 * b[2]) / 2.0).abs() < 1e-12);
    assert!((report.cycles[2].mean_vb - (100.0 * b[2] + 100.0 * b[3]) / 2.0).abs() < 1e-12);
}

#[test]
fn missing_endpoint_is_rejected_without_partial_cycle_means() {
    let b = boundaries();
    let input = trace(&[
        row(0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
        row(b[0], 1.0, 0.0, 0.0, 0.0, 0.0),
        row(b[1], 2.0, 0.0, 0.0, 0.0, 0.0),
        row(b[2], 3.0, 0.0, 0.0, 0.0, 0.0),
    ]);
    let error = metrics::analyze(Cursor::new(input)).expect_err("missing endpoint");
    assert!(error.0.contains("incomplete requested window"));
}

#[test]
fn backward_time_is_rejected() {
    let input = trace(&[
        row(0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
        row(0.7, 1.0, 0.0, 0.0, 0.0, 0.0),
        row(0.6, 2.0, 0.0, 0.0, 0.0, 0.0),
    ]);
    let error = metrics::analyze(Cursor::new(input)).expect_err("backward");
    assert!(error.0.contains("backward time"));
}

#[test]
fn nonfinite_data_is_rejected() {
    let mut fields: Vec<String> = row(0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
        .split_whitespace()
        .map(str::to_string)
        .collect();
    fields[9] = "NaN".to_string();
    let line = fields.join(" ");
    let error = metrics::analyze(Cursor::new(format!("{}\n{}\n", headers(), line)))
        .expect_err("nonfinite");
    assert!(error.0.contains("non-finite"));
}

#[test]
fn exact_cycle_boundaries_are_fully_covered() {
    let b = boundaries();
    let input = trace(&[
        row(b[0], 10.0, 1.0, 2.0, 3.0, 4.0),
        row(b[1], 20.0, 1.0, 2.0, 3.0, 4.0),
        row(b[2], 30.0, 1.0, 2.0, 3.0, 4.0),
        row(b[3], 40.0, 1.0, 2.0, 3.0, 4.0),
    ]);
    let report = metrics::analyze(Cursor::new(input)).expect("exact boundaries");
    assert!(report.cycles.iter().all(|cycle| cycle.covered));
    assert_eq!(report.duplicate_groups, 0);
}
