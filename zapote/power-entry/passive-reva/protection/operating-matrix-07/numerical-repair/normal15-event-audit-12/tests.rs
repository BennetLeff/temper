#[path = "audit.rs"]
mod audit;

use std::io::Cursor;
use std::io::Write;

fn header() -> String { audit::HEADER.join(" ") }
fn row(time: f64, acsrc: f64, acn: f64, ivac: f64, load: f64, vb: f64, il: f64, q: f64) -> String {
    [time, acsrc, acn, ivac, load, vb, il, 0.0, 0.0, 0.0, q, 5.0, 0.0, 2.0, 0.0].iter().map(|v| format!("{v:.17e}")).collect::<Vec<_>>().join(" ")
}
fn input(rows: &[String]) -> String { format!("{}\n{}\n", header(), rows.join("\n")) }
fn cfg() -> audit::Config { audit::Config { start: 0.0, end: 0.65, max_step: 1.0, load_resistance: 190.0 } }

#[test]
fn event_rows_context_and_stable_e3_are_retained() {
    let data = input(&[
        row(0.0, 1000.0, 900.0, -2.0, 10.0, 2.0, 1.0, 0.0),
        row(0.1, 1000.0, 900.0, -2.0, 10.0, 2.0, 1.0, 0.0),
        row(0.1, 1001.0, 900.0, -3.0, 10.0, 4.0, 2.0, 5.0),
        row(0.1, 1000.0, 900.0, -2.0, 10.0, 2.0, 1.0, 0.0),
        row(0.2, 1000.0, 900.0, -2.0, 10.0, 2.0, 1.0, 0.0),
        row(0.65, 1000.0, 900.0, -2.0, 10.0, 2.0, 1.0, 0.0),
    ]);
    let mut events = Vec::new();
    let report = audit::analyze(Cursor::new(data), &mut events, cfg()).expect("normal15 audit");
    assert_eq!(report.rows, 6);
    assert_eq!(report.equal_groups, 1);
    assert_eq!(report.max_group_rows, 3);
    assert_eq!(report.right_context_missing, 0);
    assert_eq!(report.exact_logic_transitions, 2);
    assert!(!report.normalized_applicable[0] && !report.normalized_applicable[10] && report.normalized_applicable[9]);
    assert!(report.e3_max_spread_j > 0.0 && report.e3_sum_absolute_j > 0.0);
    let text = String::from_utf8(events).unwrap();
    assert!(text.contains("LEFT\t1\t1\t"));
    assert!(text.contains("GROUP\t1\t4\t"));
    assert!(text.contains("RIGHT\t1\t5\t"));
}

#[test]
fn boundary_flag_and_differential_ac2_use_standard_resistance() {
    let data = input(&[
        row(0.0, 1000.0, 900.0, -2.0, 10.0, 0.0, 0.0, 0.0),
        row(0.5, 1000.0, 900.0, -2.0, 10.0, 0.0, 0.0, 0.0),
        row(0.6, 1000.0, 900.0, -2.0, 10.0, 0.0, 0.0, 0.0),
        row(0.6, 1001.0, 900.0, -2.0, 20.0, 1.0, 0.0, 0.0),
        row(0.61, 1000.0, 900.0, -2.0, 10.0, 0.0, 0.0, 0.0),
        row(0.65, 1000.0, 900.0, -2.0, 10.0, 0.0, 0.0, 0.0),
    ]);
    let mut events = Vec::new();
    let report = audit::analyze(Cursor::new(data), &mut events, cfg()).expect("boundary");
    assert_eq!(report.boundary_groups, 1);
    let ac2 = report.functions.iter().find(|f| f.name == "ac2").unwrap();
    assert_eq!(ac2.max_hull_range, 201.0);
    assert!((ac2.cycle_bounds[0] - 0.11 * 201.0).abs() < 1e-12);
    let load = report.functions.iter().find(|f| f.name == "loadP").unwrap();
    assert!((load.max_hull_range - 300.0 / 190.0).abs() < 1e-12);
    assert!((load.cycle_bounds[0] - 0.11 * 300.0 / 190.0).abs() < 1e-12);
}

#[test]
fn terminal_duplicate_is_reported_and_invalid_rows_fail_closed() {
    let terminal = input(&[
        row(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
        row(0.3, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
        row(0.65, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
        row(0.65, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
    ]);
    let mut events = Vec::new();
    let report = audit::analyze(Cursor::new(terminal), &mut events, cfg()).expect("terminal group is diagnostic");
    assert_eq!(report.right_context_missing, 1);
    let backwards = input(&[row(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0), row(0.2, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0), row(0.1, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0), row(0.65, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)]);
    assert!(audit::analyze(Cursor::new(backwards), Vec::new(), cfg()).unwrap_err().0.contains("backwards"));
    let nonfinite = input(&[row(0.0, f64::NAN, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0), row(0.65, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)]);
    assert!(audit::analyze(Cursor::new(nonfinite), Vec::new(), cfg()).unwrap_err().0.contains("non-finite"));
}

#[test]
fn exact_header_and_max_step_are_enforced() {
    let data = input(&[row(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0), row(0.65, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)]);
    let strict = audit::Config { max_step: 0.1, ..cfg() };
    assert!(audit::analyze(Cursor::new(data), Vec::new(), strict).unwrap_err().0.contains("step"));
    let bad = "time v(acsrc)\n0 0\n";
    assert!(audit::analyze(Cursor::new(bad), Vec::new(), cfg()).unwrap_err().0.contains("header"));
}

#[test]
fn cycle_boundaries_follow_shifted_end_time() {
    let end = 0.05;
    let shifted = audit::Config { end, ..cfg() };
    let boundary = 0.05 - 1.0 / 60.0;
    let data = input(&[
        row(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
        row(0.02, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
        row(boundary, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
        row(boundary, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
        row(0.04, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
        row(end, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
    ]);
    let report = audit::analyze(Cursor::new(data), Vec::new(), shifted).expect("shifted end");
    assert_eq!(report.boundary_groups, 1);
    assert!(report.functions.iter().all(|f| f.cycle_bounds.iter().all(|bound| bound.is_finite())));
}

struct FlushFails;
impl Write for FlushFails {
    fn write(&mut self, bytes: &[u8]) -> std::io::Result<usize> { Ok(bytes.len()) }
    fn flush(&mut self) -> std::io::Result<()> { Err(std::io::Error::other("synthetic flush failure")) }
}

#[test]
fn event_flush_failure_cannot_report_success() {
    let data = input(&[row(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0), row(0.65, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)]);
    let error = audit::analyze(Cursor::new(data), FlushFails, cfg()).unwrap_err();
    assert!(error.0.contains("flush"));
}

#[test]
fn nonfinite_configuration_and_derived_overflow_fail_closed() {
    let data = input(&[row(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0), row(0.65, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)]);
    let bad_r = audit::Config { load_resistance: f64::NAN, ..cfg() };
    assert!(audit::analyze(Cursor::new(data.clone()), Vec::new(), bad_r).unwrap_err().0.contains("configuration"));
    let bad_step = audit::Config { max_step: f64::INFINITY, ..cfg() };
    assert!(audit::analyze(Cursor::new(data), Vec::new(), bad_step).unwrap_err().0.contains("configuration"));
    let huge = f64::MAX;
    let overflow = input(&[
        row(0.0, huge, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
        row(0.1, huge, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
        row(0.1, huge / 2.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
        row(0.2, huge, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
        row(0.65, huge, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
    ]);
    assert!(audit::analyze(Cursor::new(overflow), Vec::new(), cfg()).unwrap_err().0.contains("range"));
}
