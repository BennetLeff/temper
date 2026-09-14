use std::{fs, path::Path};
use zapote_core::Status;
use zapote_harness::{bridge_thermal, pfc_power};

#[test]
fn retained_thermal_run_binds_to_real_pfc_currents_without_clearing_findings() {
    let root = Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
    let source =
        fs::read_to_string(root.join("power-entry/candidate/source-manifest.json")).unwrap();
    let native =
        fs::read_to_string(root.join("power-entry/evidence/native-copper-12.json")).unwrap();
    let board = fs::read_to_string(root.join("power-entry/candidate/section.kicad_pcb")).unwrap();
    let receipt = serde_json::from_slice(
        &fs::read(
            root.join("power-entry/evidence/copper-repair-2026-09-12/parent-manufacturing.json"),
        )
        .unwrap(),
    )
    .unwrap();
    let pfc = pfc_power::run(&source, &native, &board, &receipt).unwrap();
    assert_eq!(pfc.checks.status, Status::Fail);
    let report = bridge_thermal::run(
        Some(&root.join("thermal/evidence/bridge-necks-2026-09-14")),
        board.as_bytes(),
        Some(&pfc),
    );
    assert_eq!(
        report
            .findings
            .iter()
            .find(|f| f.rule.ends_with("NUMERICAL"))
            .unwrap()
            .status,
        Status::Pass
    );
    assert_eq!(report.status, Status::Indeterminate);
    assert_eq!(pfc.checks.status, Status::Fail);
    let contract = fs::read(root.join("thermal/bridge-cooling-contract.json")).unwrap();
    let cooling = bridge_thermal::run_with_contract(
        Some(&root.join("thermal/evidence/bridge-cooling-2026-09-14")),
        board.as_bytes(),
        Some(&pfc),
        Some(&contract),
    );
    assert_eq!(cooling.checked_rules.len(), 5);
    assert!(cooling
        .findings
        .iter()
        .any(|f| f.rule.ends_with("NUMERICAL") && f.status == Status::Pass));
    assert!(cooling
        .findings
        .iter()
        .any(|f| f.rule.ends_with("APPLICABILITY") && f.status == Status::Indeterminate));
    assert_eq!(pfc.checks.status, Status::Fail);
    // A numerically valid bundle cannot float free of its electrical load.
    let mut wrong_pfc = pfc;
    let branch = wrong_pfc
        .branches
        .iter_mut()
        .find(|b| b.id == "1a8c9e36-4bbf-486e-a8a9-34985b0b249e:2")
        .unwrap();
    branch.determined_rms_a = Some(14.0);
    let wrong = bridge_thermal::run_with_contract(
        Some(&root.join("thermal/evidence/bridge-cooling-2026-09-14")),
        board.as_bytes(),
        Some(&wrong_pfc),
        Some(&contract),
    );
    assert_eq!(wrong.status, Status::Fail);
    assert!(wrong
        .findings
        .iter()
        .any(|f| f.rule.ends_with("NUMERICAL") && f.status == Status::Fail));
}
