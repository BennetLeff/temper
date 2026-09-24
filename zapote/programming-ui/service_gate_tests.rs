#[path = "service_gate.rs"]
mod service_gate;

use service_gate::{evaluate, parse_cases, pin_conflicts, verify_sources, Verdict};
use std::path::Path;

#[test]
fn matrix_matches_declared_verdicts() {
    let cases = parse_cases(include_str!("service-cases.tsv")).unwrap();
    assert!(cases.len() >= 14);
    for case in cases {
        assert_eq!(evaluate(&case).verdict, case.expected, "{}", case.name);
    }
}

#[test]
fn each_adverse_case_is_individually_rejected() {
    let cases = parse_cases(include_str!("service-cases.tsv")).unwrap();
    for name in [
        "swapped-uart",
        "held-en",
        "held-io0",
        "missing-return",
        "missing-rail",
        "false-isolation",
        "backfeed",
        "duplicate-gpio",
        "reset-leaves-pfc-running",
        "reset-leaves-inverter-running",
        "reset-auto-rearms",
    ] {
        let case = cases.iter().find(|case| case.name == name).unwrap();
        assert_eq!(evaluate(case).verdict, Verdict::Rejected, "{name}");
    }
}

#[test]
fn current_source_claims_have_unresolved_gpio_conflicts() {
    let conflicts = pin_conflicts(include_str!("pin-ledger.tsv")).unwrap();
    for gpio in ["16", "17", "19", "20"] {
        assert!(conflicts.iter().any(|row| row.starts_with(gpio)), "{gpio}");
    }
}

#[test]
fn retained_expander_request_does_not_prove_stop() {
    let cases = parse_cases(include_str!("service-cases.tsv")).unwrap();
    let case = cases
        .iter()
        .find(|case| case.name == "expander-retains-request")
        .unwrap();
    assert_eq!(evaluate(case).verdict, Verdict::Indeterminate);
}

#[test]
fn source_lock_detects_byte_drift_and_missing_inputs() {
    let manifest = include_str!("sources.sha256");
    verify_sources(Path::new("."), manifest).unwrap();
    let tampered = manifest.replacen('1', "0", 1);
    assert!(verify_sources(Path::new("."), &tampered).is_err());
    let missing = manifest.lines().skip(1).collect::<Vec<_>>().join("\n");
    assert!(verify_sources(Path::new("."), &missing).is_err());
}

#[test]
fn malformed_matrix_and_ledger_fail_closed() {
    assert!(parse_cases("case\ttx_gpio\nwrong\t43").is_err());
    assert!(pin_conflicts("gpio\trole\n19\tUSB").is_err());
}
