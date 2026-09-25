#[path = "audit.rs"]
mod audit;

use std::io::Cursor;

fn header() -> String { audit::HEADER.join(" ") }
fn row(t: f64, q: f64, f2: f64, channel: f64) -> String {
    [t, 120.0, 380.0, 390.0, 10.0, 0.0, 2.0, channel, 0.0, 1.0, q, 5.0, 0.0, f2, 0.0, 5.0, 5.0].iter().map(|v| format!("{v:.17e}")).collect::<Vec<_>>().join(" ")
}
fn input(rows: &[String]) -> String { format!("{}\n{}\n", header(), rows.join("\n")) }
fn cfg() -> audit::Config { audit::Config { end: 0.65, expected_fault: 0.3, window: 0.1, observation: 0.01, turnoff: 2e-6, max_gap: 1.0, kind: audit::fault_checks::FaultKind::F2Open, bypass: false } }

#[test]
fn benign_equal_group_is_retained_without_indeterminate_flag() {
    let data = input(&[row(0.0, 5.0, 5.0, 0.0), row(0.1, 5.0, 5.0, 0.0), row(0.1, 5.0, 5.0, 0.0), row(0.2, 5.0, 5.0, 0.0), row(0.65, 5.0, 5.0, 0.0)]);
    let mut events = Vec::new();
    let report = audit::analyze(Cursor::new(data), &mut events, cfg()).expect("valid benign group");
    assert_eq!(report.equal_groups, 1);
    assert_eq!(report.equal_repeats, 1);
    assert_eq!(report.crossing_equal_groups, 0);
    assert!(report.checker_verdict.is_none()); // suffix is intentionally below the original 100-row minimum
    let text = String::from_utf8(events).unwrap();
    assert!(text.contains("LEFT\t1\t1\t") && text.contains("GROUP\t1\t3\t") && text.contains("RIGHT\t1\t4\t"));
}

#[test]
fn predicate_crossing_equal_group_is_indeterminate() {
    let data = input(&[row(0.0, 5.0, 5.0, 0.0), row(0.1, 5.0, 5.0, 0.0), row(0.1, 0.0, 5.0, 0.0), row(0.2, 0.0, 5.0, 0.0), row(0.65, 0.0, 5.0, 0.0)]);
    let report = audit::analyze(Cursor::new(data), Vec::new(), cfg()).expect("crossing group");
    assert_eq!(report.crossing_equal_groups, 1);
}

#[test]
fn exact_event_window_boundary_is_flagged_and_earlier_f2_is_preserved() {
    let mut config = cfg(); config.expected_fault = 0.5; config.window = 0.1;
    let data = input(&[row(0.0, 5.0, 5.0, 0.0), row(0.2, 5.0, 5.0, 0.0), row(0.25, 5.0, 2.0, 0.0), row(0.4, 5.0, 2.0, 0.0), row(0.4, 5.0, 2.0, 0.0), row(0.5, 5.0, 2.0, 0.0), row(0.65, 5.0, 2.0, 0.0)]);
    let report = audit::analyze(Cursor::new(data), Vec::new(), config).expect("boundary group");
    assert_eq!(report.boundary_equal_groups, 1);
    assert!(report.f2_edge_before_retained);
    assert!(report.retained_rows >= 4, "retained suffix keeps one left context row");
}

#[test]
fn global_one_microsecond_gap_is_not_replaced_by_local_pacing_rule() {
    let data = input(&[row(0.0, 5.0, 5.0, 0.0), row(0.0 + 2e-6, 5.0, 5.0, 0.0), row(0.65, 5.0, 5.0, 0.0)]);
    let mut config = cfg(); config.max_gap = 1e-6;
    assert!(audit::analyze(Cursor::new(data), Vec::new(), config).unwrap_err().0.contains("global gap"));
}

#[test]
fn all_row_node_screen_cannot_be_hidden_before_retained_window() {
    let mut config = cfg(); config.expected_fault = 0.5; config.window = 0.1;
    let mut high = row(0.1, 5.0, 5.0, 0.0);
    let mut fields: Vec<_> = high.split_whitespace().map(str::to_owned).collect();
    fields[2] = "5.010000000000000e2".into();
    high = fields.join(" ");
    let data = input(&[row(0.0, 5.0, 5.0, 0.0), high, row(0.4, 5.0, 4.0, 0.0), row(0.4, 5.0, 4.0, 0.0), row(0.65, 5.0, 4.0, 0.0)]);
    let err = audit::analyze(Cursor::new(data), Vec::new(), config).unwrap_err();
    assert!(err.0.contains("all-row node screen vd"));
}

#[test]
fn terminal_equal_group_is_reported_as_missing_right_context() {
    let mut config = cfg(); config.end = 0.2; config.expected_fault = 0.1; config.window = 0.05;
    let data = input(&[row(0.0, 5.0, 5.0, 0.0), row(0.1, 5.0, 4.0, 0.0), row(0.2, 5.0, 4.0, 0.0), row(0.2, 5.0, 4.0, 0.0)]);
    let report = audit::analyze(Cursor::new(data), Vec::new(), config).expect("terminal group diagnostic");
    assert!(report.terminal_missing_right);
}

#[test]
fn retained_suffix_cap_fails_closed_without_allocating_the_cap() {
    assert!(audit::retained_capacity(audit::RETAINED_LIMIT - 1).is_ok());
    let err = audit::retained_capacity(audit::RETAINED_LIMIT).unwrap_err();
    assert!(err.0.contains("four-million-row cap"));
}

#[test]
fn oversized_input_line_is_rejected_before_parsing_fields() {
    let mut data = input(&[row(0.0, 5.0, 5.0, 0.0), row(0.1, 5.0, 5.0, 0.0), row(0.65, 5.0, 5.0, 0.0)]);
    data.push_str(&"x".repeat(20_000));
    data.push('\n');
    let err = audit::analyze(Cursor::new(data), Vec::new(), cfg()).unwrap_err();
    assert!(err.0.contains("expected 17 fields") || err.0.contains("line exceeds"));
}

// Parent fixture: exercise the actual imported decision on a dense, complete
// stream, not only validation flags on a below-minimum synthetic suffix.
fn parent_fault_stream(duplicate_at: Option<usize>, prefix_overvoltage: bool) -> String {
    let mut lines = Vec::new();
    for i in 0..200 {
        let mut v = [i as f64 * 1e-9, 120.0, 380.0, 390.0, 10.0, 0.0, 2.0, 0.0, 0.0, 1.0,
            if i < 103 {5.0} else {0.0}, if i < 103 {5.0} else {0.0},
            if i < 101 {0.0} else {5.0}, if i < 100 {5.0} else {0.0}, 0.0, 5.0, 5.0];
        if prefix_overvoltage && i == 10 { v[2] = 501.0; }
        let line = v.iter().map(|x| format!("{x:.17e}")).collect::<Vec<_>>().join(" ");
        lines.push(line.clone());
        if duplicate_at == Some(i) { lines.push(line); }
    }
    input(&lines)
}
fn parent_cfg() -> audit::Config {
    audit::Config { end:199e-9, expected_fault:100e-9, window:10e-9, observation:20e-9,
        turnoff:2e-6,max_gap:1e-6,kind:audit::fault_checks::FaultKind::F2Open,bypass:false }
}
#[test]
fn parent_full_pipeline_retains_benign_duplicate_and_same_frozen_verdict() {
    let plain = audit::analyze(Cursor::new(parent_fault_stream(None,false)), Vec::new(), parent_cfg()).unwrap();
    let repeated = audit::analyze(Cursor::new(parent_fault_stream(Some(150),false)), Vec::new(), parent_cfg()).unwrap();
    assert!(plain.checker_verdict.as_ref().unwrap().starts_with("Pass {"));
    assert_eq!(plain.checker_verdict, repeated.checker_verdict);
    assert_eq!(repeated.rows, 201);
    assert_eq!(repeated.equal_repeats, 1);
}
#[test]
fn parent_prefix_excursion_cannot_earn_suffix_pass() {
    assert!(audit::analyze(Cursor::new(parent_fault_stream(None,true)), Vec::new(), parent_cfg()).unwrap_err().0.contains("all-row node screen vd"));
}
#[test]
fn parent_bypass_cannot_earn_pass() {
    let mut config = parent_cfg(); config.bypass = true;
    let report = audit::analyze(Cursor::new(parent_fault_stream(None,false)), Vec::new(), config).unwrap();
    assert!(report.checker_verdict.unwrap().contains("bypassed"));
}
