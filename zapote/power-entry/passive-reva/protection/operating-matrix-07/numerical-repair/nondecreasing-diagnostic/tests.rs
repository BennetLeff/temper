#[path = "audit.rs"]
mod audit;

use std::io::Cursor;

fn header() -> String {
    (0..audit::WIDTH)
        .map(|column| if column == 0 { "time".to_string() } else { format!("c{column}") })
        .collect::<Vec<_>>()
        .join(" ")
}

fn row(time: f64, overrides: &[(usize, f64)]) -> String {
    let mut values = [0.0; audit::WIDTH];
    values[0] = time;
    for &(column, value) in overrides {
        values[column] = value;
    }
    values
        .iter()
        .map(|value| format!("{value:.17e}"))
        .collect::<Vec<_>>()
        .join(" ")
}

fn trace(rows: &[String]) -> String {
    format!("{}\n{}\n", header(), rows.join("\n"))
}

#[test]
fn exact_equal_groups_and_per_column_deltas() {
    let input = trace(&[
        row(0.0, &[]),
        row(1.0, &[(3, 10.0)]),
        row(1.0, &[(3, 12.0), (7, -5.0)]),
        row(2.0, &[(1, 3.0)]),
        row(10.0, &[(2, -10.0)]),
        row(10.0, &[(2, -9.0)]),
        row(11.0, &[]),
    ]);
    let report = audit::audit(Cursor::new(input)).expect("valid groups");
    assert_eq!(report.rows, 7);
    assert_eq!(report.equal_groups, 2);
    assert_eq!(report.equal_rows, 4);
    assert_eq!(report.equal_repeats, 2);
    assert_eq!(report.max_group_rows, 2);
    assert_eq!(report.first_equal_time, Some(1.0));
    assert_eq!(report.last_equal_time, Some(10.0));
    assert_eq!(report.max_equal_delta[3].value, 2.0);
    assert_eq!(report.max_equal_delta[7].value, 5.0);
    assert_eq!(report.max_equal_delta[7].group_index, 1);
    assert_eq!(report.first_groups.len(), 2);
    assert_eq!(report.last_groups.len(), 2);
    assert_eq!(report.first_groups[0].next_dt, 1.0);
    assert_eq!(report.first_groups[1].next_dt, 1.0);
}

#[test]
fn duplicate_rows_participate_in_peaks_and_minima() {
    let input = trace(&[
        row(0.0, &[(10, 1.0), (20, -1.0)]),
        row(1.0, &[(10, 100.0), (20, -100.0)]),
        row(1.0, &[(10, 200.0), (20, -200.0)]),
        row(2.0, &[(10, 2.0), (20, -2.0)]),
    ]);
    let report = audit::audit(Cursor::new(input)).expect("valid peaks");
    assert_eq!(report.max[10].value, 200.0);
    assert_eq!(report.max[10].row, 3);
    assert_eq!(report.min[20].value, -200.0);
    assert_eq!(report.min[20].row, 3);
}

#[test]
fn widely_spaced_groups_keep_positive_progress() {
    let input = trace(&[
        row(0.0, &[]),
        row(0.0, &[(4, 1.0)]),
        row(1.0e12, &[]),
        row(1.0e12, &[(4, 2.0)]),
        row(1.0e12 + 0.5, &[]),
    ]);
    let report = audit::audit(Cursor::new(input)).expect("widely spaced groups");
    assert_eq!(report.equal_groups, 2);
    assert_eq!(report.first_groups[0].next_dt, 1.0e12);
    assert_eq!(report.first_groups[1].next_dt, 0.5);
}

#[test]
fn backward_time_is_rejected() {
    let input = trace(&[row(0.0, &[]), row(1.0, &[]), row(0.5, &[])]);
    let error = audit::audit(Cursor::new(input)).expect_err("backward time");
    assert!(error.0.contains("backward time"));
}

#[test]
fn nonfinite_field_is_rejected() {
    let mut bad = [0.0; audit::WIDTH];
    bad[0] = 1.0;
    bad[9] = f64::NAN;
    let fields = bad
        .iter()
        .map(|value| value.to_string())
        .collect::<Vec<_>>()
        .join(" ");
    let error = audit::audit(Cursor::new(format!("{}\n{}\n", header(), fields)))
        .expect_err("non-finite field");
    assert!(error.0.contains("non-finite"));
}

#[test]
fn duplicate_group_at_eof_is_rejected() {
    let input = trace(&[row(0.0, &[]), row(1.0, &[]), row(1.0, &[(8, 4.0)])]);
    let error = audit::audit(Cursor::new(input)).expect_err("end duplicate group");
    assert!(error.0.contains("at EOF"));
}
