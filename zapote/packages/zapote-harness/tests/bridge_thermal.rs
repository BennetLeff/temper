use sha2::Digest;
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

#[test]
fn physical_model_replay_binds_shared_package_and_pfc_waveform() {
    let root = Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
    let source =
        fs::read_to_string(root.join("power-entry/candidate/source-manifest.json")).unwrap();
    let native = fs::read(root.join("power-entry/evidence/native-copper-12.json")).unwrap();
    let board = fs::read(root.join("power-entry/candidate/section.kicad_pcb")).unwrap();
    let receipt: serde_json::Value = serde_json::from_slice(
        &fs::read(
            root.join("power-entry/evidence/copper-repair-2026-09-12/parent-manufacturing.json"),
        )
        .unwrap(),
    )
    .unwrap();
    let pfc = pfc_power::run(
        &source,
        std::str::from_utf8(&native).unwrap(),
        std::str::from_utf8(&board).unwrap(),
        &receipt,
    )
    .unwrap();
    let model = zapote_thermal::neck_geometry::build_neck_model(
        &native,
        &fs::read(root.join("thermal/evidence/bridge-necks-2026-09-14/manufacturing.json"))
            .unwrap(),
    )
    .unwrap();
    let manufacturing =
        fs::read(root.join("thermal/evidence/bridge-necks-2026-09-14/manufacturing.json")).unwrap();
    let mut contract = zapote_thermal::physical_model::baseline_contract(
        format!("{:x}", sha2::Sha256::digest(&board)),
        &model,
    );
    let waveform = bridge_thermal::physical_waveform(&pfc).unwrap();
    let assessment = zapote_thermal::physical_model::evaluate(&contract, &waveform).unwrap();
    let contract_bytes = serde_json::to_vec(&contract).unwrap();
    let assessment_bytes = serde_json::to_vec(&assessment).unwrap();
    let report = bridge_thermal::run_with_physical_model(
        None,
        &board,
        Some(&pfc),
        Some(&contract_bytes),
        Some(&assessment_bytes),
        None,
        Some(&native),
        Some(&manufacturing),
    );
    assert_eq!(report.status, Status::Indeterminate);
    assert!(report
        .findings
        .iter()
        .any(|f| f.rule == bridge_thermal::PHYSICAL_RULES[0] && f.status == Status::Pass));
    assert!(report.findings.iter().any(|f| {
        f.rule == bridge_thermal::PHYSICAL_RULES[1] && f.status == Status::Indeterminate
    }));

    contract.loss.pfc_profile_sha256 =
        Some(zapote_thermal::physical_model::waveform_sha256(&waveform).unwrap());
    let contract_bytes = serde_json::to_vec(&contract).unwrap();
    let stale = bridge_thermal::run_with_physical_model(
        None,
        &board,
        Some(&pfc),
        Some(&contract_bytes),
        Some(&assessment_bytes),
        None,
        Some(&native),
        Some(&manufacturing),
    );
    assert_eq!(stale.status, Status::Fail);
}

#[test]
fn retained_pretty_contract_and_source_replay_through_production_boundary() {
    let root = Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
    let source =
        fs::read_to_string(root.join("power-entry/candidate/source-manifest.json")).unwrap();
    let evidence = root.join("thermal/evidence/bridge-joints-2026-09-14/baseline");
    let native = fs::read(evidence.join("native.json")).unwrap();
    let manufacturing = fs::read(evidence.join("manufacturing.json")).unwrap();
    let board = fs::read(root.join("power-entry/candidate/section.kicad_pcb")).unwrap();
    let pfc = pfc_power::run(
        &source,
        std::str::from_utf8(&native).unwrap(),
        std::str::from_utf8(&board).unwrap(),
        &serde_json::from_slice(&manufacturing).unwrap(),
    )
    .unwrap();
    let contract = fs::read(evidence.join("physical-contract.json")).unwrap();
    let assessment = fs::read(evidence.join("physical-assessment.json")).unwrap();
    let pdf = fs::read(evidence.join("source.pdf")).unwrap();
    let r = bridge_thermal::run_with_physical_model(
        None,
        &board,
        Some(&pfc),
        Some(&contract),
        Some(&assessment),
        Some(&pdf),
        Some(&native),
        Some(&manufacturing),
    );
    assert_eq!(r.status, Status::Indeterminate, "{:?}", r.findings);
    for rule in &bridge_thermal::PHYSICAL_RULES[..2] {
        assert!(r
            .findings
            .iter()
            .any(|f| f.rule == *rule && f.status == Status::Pass));
    }
    let mut changed: zapote_thermal::physical_model::PhysicalModelContract =
        serde_json::from_slice(&contract).unwrap();
    changed.paths[0].copper_thickness_um.nominal *= 2.0;
    changed.paths[0].copper_thickness_um.max *= 2.0;
    let waveform = bridge_thermal::physical_waveform(&pfc).unwrap();
    let new_assessment =
        zapote_thermal::physical_model::evaluate_with_source_bytes(&changed, &waveform, &pdf)
            .unwrap();
    let c = serde_json::to_vec_pretty(&changed).unwrap();
    let a = serde_json::to_vec_pretty(&new_assessment).unwrap();
    let r = bridge_thermal::run_with_physical_model(
        None,
        &board,
        Some(&pfc),
        Some(&c),
        Some(&a),
        Some(&pdf),
        Some(&native),
        Some(&manufacturing),
    );
    assert_eq!(r.status, Status::Fail);
}
