use std::path::PathBuf;
use zapote_core::{CheckReport, Finding, Status};
use zapote_harness::board_check::{exit_code, summary, BoardCheckReport, NamedCheck};

fn located(rule: &str, object: &str, actual: &str, required: &str) -> Finding {
    let mut f = Finding::fail(rule, "below limit", object);
    f.actual = Some(actual.into());
    f.required = Some(required.into());
    f
}

fn report(checks: Vec<(&str, CheckReport)>) -> BoardCheckReport {
    BoardCheckReport::new(
        PathBuf::from("/b/board.kicad_pcb"),
        "ab".repeat(32),
        PathBuf::from("/b/board.kicad_sch"),
        serde_json::json!({"name": "jlcpcb-2layer-2oz"}),
        checks
            .into_iter()
            .map(|(name, report)| NamedCheck { name: name.into(), report })
            .collect(),
    )
}

#[test]
fn summary_groups_failures_by_rule_with_location_and_values() {
    let dfm = CheckReport::from_findings(
        vec![
            located("DRC.P2.TRACK_WIDTH", "T1", "0.100 mm", ">= 0.160 mm"),
            located("DRC.P2.TRACK_WIDTH", "T2", "0.120 mm", ">= 0.160 mm"),
            Finding::indeterminate("DRC.P2.DRILL_SIZE", "hole kind missing", "H9"),
        ],
        vec!["DRC.P2.TRACK_WIDTH".into()],
        vec!["assembly process is required".into()],
    );
    let r = report(vec![("manufacturing", dfm)]);
    let text = summary(&r);
    assert!(text.contains("FAIL"), "{text}");
    assert!(text.contains("DRC.P2.TRACK_WIDTH (2)"), "{text}");
    assert!(text.contains("T1: below limit [actual 0.100 mm, required >= 0.160 mm]"), "{text}");
    assert!(text.contains("indeterminate: 1"), "{text}");
    assert!(text.contains("assembly process is required"), "{text}");
}

#[test]
fn overall_status_and_exit_code_follow_the_worst_check() {
    let pass = CheckReport::from_findings(vec![], vec!["X".into()], vec![]);
    let gap = CheckReport::from_findings(vec![], vec!["Y".into()], vec!["missing input".into()]);
    let fail = CheckReport::from_findings(vec![Finding::fail("Z", "bad", "o")], vec!["Z".into()], vec![]);
    assert_eq!(exit_code(&report(vec![("a", pass.clone())])), 0);
    assert_eq!(exit_code(&report(vec![("a", pass.clone()), ("b", gap.clone())])), 2);
    let worst = report(vec![("a", pass), ("b", gap), ("c", fail)]);
    assert_eq!(worst.status, Status::Fail);
    assert_eq!(exit_code(&worst), 1);
}

/// Live KiCad run on the 120 V board. Needs KICAD_CLI and KICAD_PYTHON.
#[test]
#[ignore = "requires KiCad 10 (KICAD_CLI, KICAD_PYTHON)"]
fn live_check_of_the_120v_board_binds_inputs_and_locates_findings() {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..");
    let board = root.join("power-stage-120v/native-17/section.kicad_pcb").canonicalize().unwrap();
    let out = std::env::temp_dir().join(format!("zapote-check-live-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&out);
    let check = zapote_harness::board_check::BoardCheck {
        board: board.clone(),
        schematic: None,
        profile: root.join("fab-profiles/jlcpcb-4layer-2oz.json"),
        assembly: Some("THT wave and hand solder".into()),
        kicad_cli: std::env::var_os("KICAD_CLI").expect("KICAD_CLI").into(),
        python: std::env::var_os("KICAD_PYTHON").expect("KICAD_PYTHON").into(),
        output: out.clone(),
    };
    let r = zapote_harness::board_check::run(&check).expect("board check runs");
    let saved: serde_json::Value =
        serde_json::from_slice(&std::fs::read(out.join("report.json")).unwrap()).unwrap();
    assert_eq!(saved["board_sha256"], zapote_harness::runner::digest(&std::fs::read(&board).unwrap()));
    assert_eq!(saved["profile"]["name"], "jlcpcb-4layer-2oz");
    for key in ["receipt_sha256", "extractor_sha256"] {
        assert_eq!(saved["manufacturing"][key].as_str().map(str::len), Some(64), "{key}");
    }
    let dfm = &r.checks.iter().find(|c| c.name == "manufacturing").unwrap().report;
    assert!(!dfm.coverage_gaps.iter().any(|g| g.contains("assembly process")), "{:?}", dfm.coverage_gaps);
    let names: Vec<_> = r.checks.iter().map(|c| c.name.as_str()).collect();
    assert_eq!(names, ["stackup", "native", "manufacturing", "fab"]);
    assert_eq!(saved["fab"]["rules_sha256"].as_str().map(str::len), Some(64));
    assert_eq!(saved["fab"]["board_sha256"], saved["board_sha256"]);
    let fab = &r.checks.iter().find(|c| c.name == "fab").unwrap().report;
    assert!(fab.coverage_gaps.is_empty(), "{:?}", fab.coverage_gaps);
    assert!(fab.findings.iter().all(|f| f.rule.starts_with("FAB.")), "{:#?}", fab.findings);
    for c in &r.checks {
        for f in &c.report.findings {
            assert!(!f.rule.is_empty() && !f.object.is_empty(), "{f:?}");
        }
    }
    let _ = std::fs::remove_dir_all(&out);
}

#[test]
fn summary_says_when_the_fab_pass_ran_without_a_project() {
    let fab = CheckReport::from_findings(vec![Finding::pass("FAB.clearance", "0 violations", "board")], vec![], vec![]);
    let mut r = report(vec![("fab", fab)]);
    r.fab = Some(serde_json::json!({"project_sha256": null}));
    assert!(summary(&r).contains("no .kicad_pro beside the board"), "{}", summary(&r));
    r.fab = Some(serde_json::json!({"project_sha256": "ab"}));
    assert!(!summary(&r).contains("no .kicad_pro"), "{}", summary(&r));
}
