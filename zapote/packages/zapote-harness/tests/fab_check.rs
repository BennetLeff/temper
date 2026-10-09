//! The fab pass's judgement of KiCad reports. The live KiCad runs are
//! `#[ignore]`d (CI has no KiCad); these use a report KiCad 10.0.4 wrote for
//! the committed self-test board under the 2-layer 2 oz profile's rules.
use serde_json::{json, Value};
use zapote_core::Status;
use zapote_drc::fab_profile::parse_profile;
use zapote_drc::fab_rules::kicad_rules;
use zapote_harness::fab_check::{evaluate, rule_set};
use zapote_harness::native_reports::{drc_report, DrcReport};

const SELFTEST: &str = include_str!("../fixtures/fab_selftest-drc.json");

fn rules() -> Vec<zapote_harness::fab_check::FabRule> {
    let limits = parse_profile(include_str!("../../../fab-profiles/jlcpcb-2layer-2oz.json")).unwrap();
    rule_set(&kicad_rules(&limits).unwrap())
}

fn report(edit: impl FnOnce(&mut Value)) -> DrcReport {
    let mut v: Value = serde_json::from_str(SELFTEST).unwrap();
    edit(&mut v);
    drc_report(&v.to_string()).unwrap()
}

#[test]
fn rule_set_names_each_rule_and_its_constraint() {
    let r = rules();
    assert_eq!(r.len(), 8);
    assert!(r.iter().any(|r| r.name == "zapote fab NPTH hole to copper" && r.constraint == "hole_clearance"));
    assert!(r.iter().any(|r| r.name == "zapote fab silk text height B" && r.constraint == "text_height"));
}

#[test]
fn only_fab_rule_violations_become_located_fab_findings() {
    let selftest = report(|_| {});
    let r = evaluate(&rules(), &selftest, &selftest);
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
    let selftest = report(|_| {});
    let clean = report(|v| v["violations"] = json!([]));
    let r = evaluate(&rules(), &selftest, &clean);
    assert_eq!(r.status, Status::Pass, "{r:#?}");
    for rule in ["FAB.clearance", "FAB.hole_clearance", "FAB.text_height", "FAB.text_thickness"] {
        assert!(r.checked_rules.iter().any(|c| c == rule), "{rule}");
    }
    assert_eq!(r.findings.iter().filter(|f| f.status == Status::Pass).count(), 8);
}

#[test]
fn a_rule_kicad_did_not_apply_on_the_self_test_board_is_a_gap() {
    // KiCad ignores a malformed .kicad_dru without an error (measured on
    // 10.0.4); the self-test board is how the pass notices.
    let selftest = report(|v| {
        let list = v["violations"].as_array_mut().unwrap();
        list.retain(|x| !x["description"].as_str().unwrap().contains("'zapote fab via hole to copper'"));
    });
    let clean = report(|v| v["violations"] = json!([]));
    let r = evaluate(&rules(), &selftest, &clean);
    assert_eq!(r.status, Status::Indeterminate);
    assert!(r.coverage_gaps.iter().any(|g| g.contains("zapote fab via hole to copper")), "{:?}", r.coverage_gaps);
    assert!(!r.findings.iter().any(|f| f.status == Status::Pass && f.message.contains("via hole")), "{r:#?}");
}

#[test]
fn a_check_the_board_project_ignores_is_a_gap() {
    let selftest = report(|_| {});
    let board = report(|v| {
        v["violations"] = json!([]);
        v["ignored_checks"].as_array_mut().unwrap().push(json!({"key": "hole_clearance", "description": "Hole clearance"}));
    });
    let r = evaluate(&rules(), &selftest, &board);
    assert_eq!(r.status, Status::Indeterminate);
    assert!(r.coverage_gaps.iter().any(|g| g.contains("hole_clearance")), "{:?}", r.coverage_gaps);
}

#[test]
fn a_profile_without_fab_pass_limits_has_no_fab_check() {
    let out = std::env::temp_dir().join(format!("zapote-fab-none-{}", std::process::id()));
    let limits = zapote_drc::manufacturing::FabricationLimits::default();
    let r = zapote_harness::fab_check::fab_check(
        std::path::Path::new("/nonexistent/board.kicad_pcb"),
        &out,
        std::path::Path::new("/nonexistent/kicad-cli"),
        &limits,
    );
    assert!(matches!(r, Ok(None)));
    assert!(!out.exists(), "nothing is written when the check is absent");
}

/// Live: the committed self-test board as the input board. Needs KICAD_CLI.
#[test]
#[ignore = "requires KiCad 10 (KICAD_CLI)"]
fn live_fab_pass_on_the_self_test_board() {
    let board = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("fixtures/fab_selftest.kicad_pcb");
    let before = std::fs::read(&board).unwrap();
    let out = std::env::temp_dir().join(format!("zapote-fab-live-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&out);
    let limits = parse_profile(include_str!("../../../fab-profiles/jlcpcb-2layer-2oz.json")).unwrap();
    let kicad = std::path::PathBuf::from(std::env::var_os("KICAD_CLI").expect("KICAD_CLI"));
    let r = zapote_harness::fab_check::fab_check(&board, &out, &kicad, &limits).unwrap().unwrap();
    assert_eq!(std::fs::read(&board).unwrap(), before, "input board untouched");
    assert!(r.report.coverage_gaps.is_empty(), "{:?}", r.report.coverage_gaps);
    assert_eq!(r.report.findings.iter().filter(|f| f.status == Status::Fail).count(), 10);
    assert_eq!(r.evidence["project_sha256"], Value::Null);
    assert_eq!(r.evidence["rules"].as_array().unwrap().len(), 8);
    let _ = std::fs::remove_dir_all(&out);
}
