use sha2::{Digest, Sha256};
use std::{fs, path::Path};
use zapote_thermal::bridge_cooling;

fn clone_tree(source: &Path, target: &Path) {
    fs::create_dir(target).unwrap();
    for entry in fs::read_dir(source).unwrap() {
        let entry = entry.unwrap();
        let out = target.join(entry.file_name());
        if entry.file_type().unwrap().is_dir() {
            clone_tree(&entry.path(), &out);
        } else if fs::hard_link(entry.path(), &out).is_err() {
            fs::copy(entry.path(), out).unwrap();
        }
    }
}

// Never modify a shared fixture inode through a hard link.
fn replace(path: &Path, bytes: &[u8]) {
    let temporary = path.with_extension("replacement");
    fs::write(&temporary, bytes).unwrap();
    fs::rename(temporary, path).unwrap();
}

#[test]
fn cooling_replay_rejects_rehashed_contract_summary_and_missing_process_evidence() {
    let zapote = Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
    let source = zapote.join("thermal/evidence/bridge-cooling-2026-09-14");
    let board = fs::read(zapote.join("power-entry/candidate/section.kicad_pcb")).unwrap();
    let contract = fs::read(zapote.join("thermal/bridge-cooling-contract.json")).unwrap();
    let report = bridge_cooling::replay(&source, &board, &contract).unwrap();
    assert_eq!(report.status, bridge_cooling::QUALIFICATION_STATUS);
    assert!(report.design_budget_compliant);
    assert!(!report.failed_fan_budget_compliant);
    assert_eq!(report.per_net.len(), 4);
    assert!(bridge_cooling::replay(&source, b"stale PCB", &contract).is_err());

    for mutation in [
        "budget",
        "qualification",
        "contract",
        "retained-only",
        "assembly",
        "command",
    ] {
        let temp = std::env::temp_dir().join(format!(
            "zapote-cooling-mutation-{}-{mutation}",
            std::process::id()
        ));
        clone_tree(&source, &temp);
        let mut summary: serde_json::Value =
            serde_json::from_slice(&fs::read(temp.join("assessment.json")).unwrap()).unwrap();
        let mut expected_contract = contract.clone();
        match mutation {
            "budget" => summary["budget"]["junction_c"] = 90.0.into(),
            "qualification" => summary["status"] = "qualified".into(),
            "retained-only" => {
                let mut altered = contract.clone();
                altered.push(b' ');
                replace(&temp.join("contract.json"), &altered);
            }
            "assembly" => {
                let mut changed: serde_json::Value = serde_json::from_slice(&contract).unwrap();
                changed["fan_quantity"] = 1.into();
                expected_contract = serde_json::to_vec_pretty(&changed).unwrap();
                replace(&temp.join("contract.json"), &expected_contract);
                summary["fan_quantity"] = 1.into();
                summary["contract_sha256"] =
                    format!("{:x}", Sha256::digest(&expected_contract)).into();
            }
            "contract" => {
                let mut changed: serde_json::Value = serde_json::from_slice(&contract).unwrap();
                changed["terminal_limit_c"] = 94.0.into();
                expected_contract = serde_json::to_vec_pretty(&changed).unwrap();
                replace(&temp.join("contract.json"), &expected_contract);
                summary["contract_sha256"] =
                    format!("{:x}", Sha256::digest(&expected_contract)).into();
                // Even refreshing the outer identity must not make old SIFs
                // evidence for the new reservoir temperature.
            }
            _ => {
                let inner_root = temp.join("neck-run");
                let relative = "minus--design-coarse/solver.command.json";
                fs::remove_file(inner_root.join(relative)).unwrap();
                let mut inner: serde_json::Value =
                    serde_json::from_slice(&fs::read(inner_root.join("assessment.json")).unwrap())
                        .unwrap();
                inner["artifacts"].as_object_mut().unwrap().remove(relative);
                let bytes = serde_json::to_vec_pretty(&inner).unwrap();
                replace(&inner_root.join("assessment.json"), &bytes);
                summary["inner_assessment_sha256"] = format!("{:x}", Sha256::digest(&bytes)).into();
            }
        }
        replace(
            &temp.join("assessment.json"),
            &serde_json::to_vec_pretty(&summary).unwrap(),
        );
        assert!(
            bridge_cooling::replay(&temp, &board, &expected_contract).is_err(),
            "accepted {mutation}"
        );
        fs::remove_dir_all(temp).unwrap();
    }
}
