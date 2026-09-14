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
}
