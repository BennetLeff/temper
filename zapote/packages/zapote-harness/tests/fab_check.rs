//! The fab pass's judgement of KiCad reports. The live KiCad runs are
//! `#[ignore]`d (CI has no KiCad); the others use a report KiCad 10.0.4 wrote
//! for the committed self-test board under the 2-layer 2 oz profile's rules.
use serde_json::{json, Value};
use std::path::{Path, PathBuf};
use zapote_core::Status;
use zapote_drc::fab_profile::parse_profile;
use zapote_drc::fab_rules::{rules, KicadRule};
use zapote_harness::fab_check::{evaluate, fab_check, FabInputs};
use zapote_harness::native_reports::{drc_report, DrcReport};

const SELFTEST: &str = include_str!("../fixtures/fab_selftest-drc.json");
const TWO_LAYER_2OZ: &str = include_str!("../../../fab-profiles/jlcpcb-2layer-2oz.json");
/// The board `fab_selftest-drc.json` was made from; regenerate the report when it changes.
const SELFTEST_BOARD_SHA256: &str = "5fc3734e3c0894d3c0abd5a7556fc259dc2fac26bddb3d5365884ad919fa20f2";

fn fab_rules() -> Vec<KicadRule> {
    rules(&parse_profile(TWO_LAYER_2OZ).unwrap())
}

fn report(edit: impl FnOnce(&mut Value)) -> DrcReport {
    let mut v: Value = serde_json::from_str(SELFTEST).unwrap();
    edit(&mut v);
    drc_report(&v.to_string()).unwrap()
}

fn with_violations(list: Value) -> DrcReport {
    report(|v| v["violations"] = list)
}

fn violation(kind: &str, description: &str) -> Value {
    json!({"type": kind, "severity": "error", "description": description,
           "items": [{"description": "Track [B] on F.Cu", "pos": {"x": 1.0, "y": 2.0}, "uuid": "u"}]})
}

#[test]
fn the_fixture_report_belongs_to_the_committed_self_test_board() {
    let board = std::fs::read(PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("fixtures/fab_selftest.kicad_pcb"));
    assert_eq!(zapote_harness::runner::digest(&board.unwrap()), SELFTEST_BOARD_SHA256);
}

#[test]
fn only_fab_rule_violations_become_located_fab_findings() {
    let selftest = report(|_| {});
    let r = evaluate(&fab_rules(), &selftest, &selftest);
    assert_eq!(r.status, Status::Fail);
    assert!(r.coverage_gaps.is_empty(), "{:?}", r.coverage_gaps);
    let failing: Vec<_> = r.findings.iter().filter(|f| f.status == Status::Fail).collect();
    // annular_width, via_diameter and dangling tracks are board-setup findings
    // that belong to the native pass, not to the vendor.
    assert_eq!(failing.len(), 10, "{failing:#?}");
    assert!(failing.iter().all(|f| f.rule.starts_with("FAB.")), "{failing:#?}");
    let npth = failing
        .iter()
        .find(|f| f.message.contains("'zapote fab NPTH hole to copper'"))
        .expect("NPTH finding");
    assert_eq!(npth.rule, "FAB.hole_clearance");
    assert_eq!(npth.actual.as_deref(), Some("0.0100 mm"));
    assert_eq!(npth.required.as_deref(), Some("0.2000 mm"));
    assert!(npth.object.contains("NPTH pad of J1"), "{}", npth.object);
}

#[test]
fn a_board_without_fab_violations_passes_every_rule() {
    let r = evaluate(&fab_rules(), &report(|_| {}), &with_violations(json!([])));
    assert_eq!(r.status, Status::Pass, "{r:#?}");
    for rule in ["FAB.clearance", "FAB.hole_clearance", "FAB.text_height", "FAB.text_thickness"] {
        assert!(r.checked_rules.iter().any(|c| c == rule), "{rule}");
    }
    assert_eq!(r.findings.iter().filter(|f| f.status == Status::Pass).count(), 8);
}

#[test]
fn board_and_netclass_names_cannot_impersonate_a_fab_rule() {
    let board = with_violations(json!([
        violation("clearance", "Clearance violation (rule 'board keepout' clearance 0.5000 mm; actual 0.1000 mm)"),
        violation(
            "clearance",
            "Clearance violation (netclass 'x (rule 'zapote fab copper clearance' y' clearance 0.2000 mm; actual 0.1000 mm)"
        ),
    ]));
    let r = evaluate(&fab_rules(), &report(|_| {}), &board);
    assert_eq!(r.status, Status::Pass, "{r:#?}");
}

#[test]
fn a_violation_type_that_does_not_match_its_rule_breaks_the_report_contract() {
    let board = with_violations(json!([violation(
        "hole_clearance",
        "Hole clearance violation (rule 'zapote fab copper clearance' clearance 0.1600 mm; actual 0.1000 mm)"
    )]));
    let r = evaluate(&fab_rules(), &report(|_| {}), &board);
    assert_eq!(r.status, Status::Fail);
    assert!(r.findings.iter().any(|f| f.rule == "FAB.REPORT_CONTRACT" && f.status == Status::Fail), "{r:#?}");
}

#[test]
fn a_rule_kicad_did_not_apply_on_the_self_test_board_is_a_gap() {
    // KiCad ignores a malformed .kicad_dru without an error (measured on
    // 10.0.4); the self-test board is how the pass notices.
    let selftest = report(|v| {
        let list = v["violations"].as_array_mut().unwrap();
        list.retain(|x| !x["description"].as_str().unwrap().contains("'zapote fab via hole to copper'"));
    });
    let r = evaluate(&fab_rules(), &selftest, &with_violations(json!([])));
    assert_eq!(r.status, Status::Indeterminate);
    let gap = r.coverage_gaps.iter().find(|g| g.contains("zapote fab via hole to copper")).expect("gap");
    assert!(gap.contains("at or below the self-test board's geometry"), "{gap}");
    assert!(!r.findings.iter().any(|f| f.status == Status::Pass && f.message.contains("via hole")), "{r:#?}");
}

#[test]
fn a_check_the_board_project_ignores_is_a_gap() {
    let board = report(|v| {
        v["violations"] = json!([]);
        let ignored = v["ignored_checks"].as_array_mut().unwrap();
        ignored.push(json!({"key": "hole_clearance", "description": "Hole clearance"}));
    });
    let r = evaluate(&fab_rules(), &report(|_| {}), &board);
    assert_eq!(r.status, Status::Indeterminate);
    assert!(r.coverage_gaps.iter().any(|g| g.contains("hole_clearance")), "{:?}", r.coverage_gaps);
}

#[test]
fn a_profile_without_fab_pass_limits_has_no_fab_check() {
    let out = std::env::temp_dir().join(format!("zapote-fab-none-{}", std::process::id()));
    let inputs = FabInputs {
        board: Path::new("/nonexistent/board.kicad_pcb"),
        board_bytes: b"",
        out: &out,
        kicad: Path::new("/nonexistent/kicad-cli"),
        python: Path::new("/nonexistent/python"),
    };
    let r = fab_check(&inputs, &zapote_drc::manufacturing::FabricationLimits::default());
    assert!(matches!(r, Ok(None)));
    assert!(!out.exists(), "nothing is written when the check is absent");
}

fn live(fixture: &str) -> (zapote_harness::fab_check::FabCheck, Vec<std::ffi::OsString>) {
    let dir = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("fixtures");
    let listing = || {
        let mut names: Vec<_> = std::fs::read_dir(&dir).unwrap().map(|e| e.unwrap().file_name()).collect();
        names.sort();
        names
    };
    let before = listing();
    let board = dir.join(fixture);
    let bytes = std::fs::read(&board).unwrap();
    let out = std::env::temp_dir().join(format!("zapote-fab-live-{fixture}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&out);
    let kicad = PathBuf::from(std::env::var_os("KICAD_CLI").expect("KICAD_CLI"));
    let python = PathBuf::from(std::env::var_os("KICAD_PYTHON").expect("KICAD_PYTHON"));
    let inputs = FabInputs { board: &board, board_bytes: &bytes, out: &out, kicad: &kicad, python: &python };
    let r = fab_check(&inputs, &parse_profile(TWO_LAYER_2OZ).unwrap()).unwrap().unwrap();
    assert_eq!(std::fs::read(&board).unwrap(), bytes, "input board untouched");
    assert_eq!(listing(), before, "nothing written beside the input board");
    let _ = std::fs::remove_dir_all(&out);
    (r, before)
}

/// Live: the committed self-test board as the input board.
#[test]
#[ignore = "requires KiCad 10 (KICAD_CLI, KICAD_PYTHON)"]
fn live_fab_pass_on_the_self_test_board() {
    let (r, _) = live("fab_selftest.kicad_pcb");
    assert!(r.report.coverage_gaps.is_empty(), "{:?}", r.report.coverage_gaps);
    assert_eq!(r.report.findings.iter().filter(|f| f.status == Status::Fail).count(), 10);
    assert_eq!(r.evidence["project_sha256"], Value::Null);
    assert_eq!(r.evidence["rules"].as_array().unwrap().len(), 8);
}

/// Live: a pad's local clearance must not hide a gap below the vendor limit.
#[test]
#[ignore = "requires KiCad 10 (KICAD_CLI, KICAD_PYTHON)"]
fn live_local_clearance_override_does_not_hide_a_fab_violation() {
    let (r, _) = live("fab_override_probe.kicad_pcb");
    assert_eq!(r.evidence["cleared_overrides"], json!([{"kind": "pad", "item": "J1.1", "clearance_mm": 0.05}]));
    let clearance: Vec<_> =
        r.report.findings.iter().filter(|f| f.rule == "FAB.clearance" && f.status == Status::Fail).collect();
    assert_eq!(clearance.len(), 1, "{:#?}", r.report.findings);
    assert_eq!(clearance[0].actual.as_deref(), Some("0.1000 mm"));
}
