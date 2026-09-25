#[path = "bounds.rs"]
mod bounds;

use std::io::Cursor;

const HEADERS: [&str; 31] = [
    "time", "v(acsrc)", "v(acn)", "i(Vac)", "v(load)", "v(vb)", "i(Lboost)",
    "v(vd)", "v(sw)", "v(gate)", "v(q)", "v(en)", "v(fault)", "v(vcomp)",
    "v(icomp)", "v(xu.raw)", "v(xu.pwm_hold)", "v(pwm)", "v(pwm_input)",
    "v(xdriver.driver_req)", "v(xdriver.drv_delay)", "v(xu.phase)", "v(xu.blank)",
    "v(isense)", "v(xu.ov)", "v(xu.fault)", "v(xu.pcl_hold)", "v(xu.pcl_request)",
    "v(disable)", "v(xu.m1)", "v(xu.m2)",
];

fn header() -> String { HEADERS.join("\t") }

fn event(role: &str, group: u64, source: u64, time: f64, updates: &[(usize, f64)]) -> String {
    let mut values = [0.0_f64; 31];
    values[0] = time;
    for &(index, value) in updates { values[index] = value; }
    format!("{role}\t{group}\t{source}\t{}\n", values.iter().map(|v| format!("{v:.17e}")).collect::<Vec<_>>().join("\t"))
}

fn run(lines: String) -> bounds::BoundsReport { bounds::analyze(Cursor::new(lines)).expect("valid event artifact") }

#[test]
fn group_range_keeps_internal_return_peak() {
    let mut text = format!("role\tgroup_id\tsource_row\t{}\n", header());
    text.push_str(&event("LEFT", 1, 1, 0.0, &[(1, 0.0)]));
    text.push_str(&event("GROUP", 1, 2, 1.0, &[(1, 1.0)]));
    text.push_str(&event("GROUP", 1, 3, 1.0, &[(1, 9.0)]));
    text.push_str(&event("GROUP", 1, 4, 1.0, &[(1, 1.0)]));
    text.push_str(&event("RIGHT", 1, 5, 2.0, &[(1, 0.0)]));
    let report = run(text);
    let vac = report.functions.iter().find(|f| f.name == "vac").unwrap();
    // The conservative interpolation hull includes the contexts (0..9).
    assert_eq!(vac.max_group_range, 9.0);
}

#[test]
fn linear_vb_bound_uses_both_adjacent_widths() {
    let mut text = format!("role\tgroup_id\tsource_row\t{}\n", header());
    text.push_str(&event("LEFT", 1, 1, 0.0, &[(5, 2.0)]));
    text.push_str(&event("GROUP", 1, 2, 2.0, &[(5, 2.0)]));
    text.push_str(&event("GROUP", 1, 3, 2.0, &[(5, 4.0)]));
    text.push_str(&event("RIGHT", 1, 4, 3.0, &[(5, 2.0)]));
    let report = run(text);
    let vb = report.functions.iter().find(|f| f.name == "VB").unwrap();
    // Full adjacent-width charge: (2 s + 1 s) * range(2 V) = 6 V*s.
    assert!((vb.whole_prefix_bound - 6.0).abs() < 1e-12);
}

#[test]
fn cross_product_bound_covers_negative_intervals_and_boundary() {
    let mut text = format!("role\tgroup_id\tsource_row\t{}\n", header());
    text.push_str(&event("LEFT", 1, 1, 0.59, &[(1, -2.0), (2, 1.0), (3, -2.0)]));
    text.push_str(&event("GROUP", 1, 2, 0.6, &[(1, -2.0), (2, 1.0), (3, -2.0)]));
    text.push_str(&event("GROUP", 1, 3, 0.6, &[(1, 3.0), (2, 4.0), (3, 3.0)]));
    text.push_str(&event("RIGHT", 1, 4, 0.61, &[(1, -2.0), (2, 1.0), (3, -2.0)]));
    let report = run(text);
    let input = report.functions.iter().find(|f| f.name == "inputP").unwrap();
    // vac in [-6,2], Iin in [-3,2], so corner-product range is 30.
    assert_eq!(input.max_group_range, 30.0);
    assert_eq!(report.groups_at_cycle_boundaries, 1);
    assert!(input.cycle_bounds[0] > 0.0);
}

#[test]
fn malformed_event_schema_is_rejected() {
    let bad = "role\tgroup_id\tsource_row\ttime\nLEFT\t1\t1\t0\n";
    assert!(bounds::analyze(Cursor::new(bad)).is_err());
}

#[test]
fn ac2_uses_differential_ac_voltage_not_raw_source() {
    let mut text = format!("role\tgroup_id\tsource_row\t{}\n", header());
    text.push_str(&event("LEFT", 1, 1, 0.0, &[(1, 1000.0), (2, 900.0)]));
    text.push_str(&event("GROUP", 1, 2, 1.0, &[(1, 1000.0), (2, 900.0)]));
    text.push_str(&event("GROUP", 1, 3, 1.0, &[(1, 1001.0), (2, 900.0)]));
    text.push_str(&event("RIGHT", 1, 4, 2.0, &[(1, 1000.0), (2, 900.0)]));
    let report = run(text);
    let ac2 = report.functions.iter().find(|f| f.name == "ac2").unwrap();
    assert!((ac2.max_group_range - 201.0).abs() < 1e-12);
}

#[test]
fn parent_energy_overflow_and_source_adjacency_fail_closed() {
    let mut text = format!("role\tgroup_id\tsource_row\t{}\n", header());
    text.push_str(&event("LEFT", 1, 1, 0.59, &[(6, 0.0)]));
    text.push_str(&event("GROUP", 1, 2, 0.6, &[(6, 0.0)]));
    text.push_str(&event("GROUP", 1, 3, 0.6, &[(6, 1e308)]));
    text.push_str(&event("RIGHT", 1, 4, 0.61, &[(6, 0.0)]));
    assert!(bounds::analyze(Cursor::new(text.clone())).unwrap_err().0.contains("non-finite"));
    let bad = text.replace("GROUP\t1\t3\t", "GROUP\t1\t5\t");
    assert!(bounds::analyze(Cursor::new(bad)).unwrap_err().0.contains("adjacent"));
}
