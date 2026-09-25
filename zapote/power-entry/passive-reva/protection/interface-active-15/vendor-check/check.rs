use std::{env, fs};
fn main() {
    let path = env::args().nth(1).expect("measurement log path required");
    let log = fs::read_to_string(path).expect("read measurement log");
    let expected = [
        ("premature_start", false),
        ("authorized", true),
        ("first_start", true),
        ("fault_auth", false),
        ("fault_run", false),
        ("held_session_recovery", false),
        ("stale_start", false),
        ("fresh_session", true),
        ("held_start_no_enable", false),
        ("fresh_start", true),
    ];
    let mut failed = 0;
    for (name, high) in expected {
        let values: Vec<f64> = log
            .lines()
            .filter_map(|line| {
                let (key, value) = line.split_once('=')?;
                if key.trim() != name {
                    return None;
                }
                Some(value.trim().parse().expect("invalid measurement"))
            })
            .collect();
        let passed = values.len() == 1
            && values[0].is_finite()
            && if high {
                values[0] > 4.5 && values[0] < 5.1
            } else {
                values[0].abs() < 0.1
            };
        println!(
            "{name}: {} {values:?}",
            if passed { "PASS" } else { "FAIL" }
        );
        if !passed {
            failed += 1;
        }
    }
    assert_eq!(failed, 0, "manufacturer-model functional assertions failed");
}
