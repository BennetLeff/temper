//! A valid local heat-spreading experiment never qualifies the whole shunt.
use std::path::Path;
use zapote_core::{CheckReport, Finding};
pub const RULES: [&str; 3] = [
    "THERMAL.PFC.SHUNT_LOCAL_NUMERICAL",
    "THERMAL.PFC.SHUNT_ASSEMBLY",
    "THERMAL.PFC.SHUNT_ASSEMBLY_NUMERICAL",
];

use crate::thermal_identity::reviewed_boost_identity_input;

pub fn run(
    root: Option<&Path>,
    assembly_root: Option<&Path>,
    native: &[u8],
    pfc: Option<&crate::pfc_power::Report>,
) -> CheckReport {
    let numerical = match root {
        None => Finding::indeterminate(RULES[0], "no retained local shunt model supplied", "shunt"),
        Some(root) => {
            let result = (|| -> anyhow::Result<_> {
                let pfc =
                    pfc.ok_or_else(|| anyhow::anyhow!("source-bound PFC waveform missing"))?;
                let s = &pfc.shunt_stress;
                anyhow::ensure!(
                    s.mpn == "HCSM2818FT10L0"
                        && (s.resistance_ohm - 0.01).abs() < 1e-12
                        && (s.rms_current_a - 15.).abs() < 1e-8,
                    "retained heat input differs from source-bound waveform/part"
                );
                let (retained, note) = reviewed_boost_identity_input(native, root)?;
                Ok((zapote_thermal::shunt_local::replay(&retained, root)?, note))
            })();
            match result {
                Ok((r,note)) => Finding::pass(RULES[0], format!("{} source-bound solves: mesh geometry, heat balance, convergence, boundary/material sensitivities and retained decks/logs verified{note}", r.cases.len()), "shunt"),
                Err(e) => Finding::fail(RULES[0], format!("local shunt replay rejected: {e:#}"), "shunt"),
            }
        }
    };
    let assembly = match assembly_root {
        None => {
            Finding::indeterminate(RULES[2], "no retained assembly heat-path evidence", "shunt")
        }
        Some(root) => {
            let result = (|| -> anyhow::Result<_> {
                let stress = &pfc
                    .ok_or_else(|| anyhow::anyhow!("source-bound PFC waveform missing"))?
                    .shunt_stress;
                anyhow::ensure!(
                    stress.mpn == "HCSM2818FT10L0"
                        && (stress.resistance_ohm - 0.01).abs() < 1e-12
                        && (stress.rms_current_a - 15.).abs() < 1e-8,
                    "assembly heat input differs from source-bound waveform/part"
                );
                let (retained, note) = reviewed_boost_identity_input(native, root)?;
                Ok((
                    zapote_thermal::shunt_assembly::replay(&retained, root)?,
                    note,
                ))
            })();
            match result {
                Ok((r,note))=>Finding::pass(RULES[2],format!("{} native copper/via/substrate/solder solves verified; internal resistor and enclosure parameters remain unresolved{note}",r.cases.len()),"shunt"),
                Err(e)=>Finding::fail(RULES[2],format!("assembly replay rejected: {e:#}"),"shunt"),
            }
        }
    };
    CheckReport::from_findings(vec![numerical,assembly,Finding::indeterminate(RULES[1], "5 W requires 500 mm² copper and resistor surface below 100 C. The heat-path study adds native vias/back copper/substrate and assumed solder, but its crop temperatures, heat split and material properties are sensitivity inputs. Internal resistor thermal resistance, full-board cooling, other component/copper losses and pulse capability remain unresolved", "shunt")], RULES.map(str::to_owned).to_vec(), vec![])
}

#[cfg(test)]
mod tests {
    use super::*;
    use zapote_core::Status;
    #[test]
    fn identical_tampered_retained_input_cannot_bypass_hash_validation() {
        let root =
            Path::new(env!("CARGO_MANIFEST_DIR")).join("../../power-entry/shunt-assembly/run-15");
        let mut value: serde_json::Value =
            serde_json::from_slice(&std::fs::read(root.join("native.json")).unwrap()).unwrap();
        let original = value.clone();
        let scratch =
            std::env::temp_dir().join(format!("zapote-transfer-hash-{}", std::process::id()));
        std::fs::create_dir(&scratch).unwrap();
        for field in ["board_sha256", "extractor_sha256"] {
            value = original.clone();
            value[field] = "0".repeat(64).into();
            let bytes = serde_json::to_vec(&value).unwrap();
            std::fs::write(scratch.join("native.json"), &bytes).unwrap();
            let result = reviewed_boost_identity_input(&bytes, &scratch);
            assert!(
                result.is_err(),
                "identical retained {field} mutation accepted"
            );
        }
        std::fs::remove_dir_all(&scratch).unwrap();
    }

    #[test]
    fn historical_transfer_rejects_any_other_saved_board_or_native_change() {
        let root = Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
        let retained = root.join("power-entry/shunt-assembly/run-15");
        let bytes =
            std::fs::read(root.join("power-entry/shunt-repair/evidence/native-04.json")).unwrap();
        let (historical, note) = reviewed_boost_identity_input(&bytes, &retained).unwrap();
        assert_eq!(
            historical,
            std::fs::read(retained.join("native.json")).unwrap()
        );
        assert!(note.contains("geometry-only") && note.contains("unqualified"));
        let original: serde_json::Value = serde_json::from_slice(&bytes).unwrap();
        for mutation in [
            "hash_only",
            "extractor",
            "board",
            "stale_hash",
            "trace",
            "component",
            "identity",
            "stackup",
            "extra",
        ] {
            let mut changed = original.clone();
            match mutation {
                "hash_only" => changed["board_sha256"] = "0".repeat(64).into(),
                "extractor" => changed["extractor_sha256"] = "0".repeat(64).into(),
                "board" | "stale_hash" => {
                    let board = format!("{}\n", changed["board_file_utf8"].as_str().unwrap());
                    if mutation == "board" {
                        changed["board_sha256"] = crate::runner::digest(board.as_bytes()).into();
                    }
                    changed["board_file_utf8"] = board.into();
                }
                "trace" => changed["traces"][0]["width_mm"] = 0.01.into(),
                "component" => changed["components"][0]["mpn"] = "unreviewed".into(),
                "identity" => {
                    for c in changed["components"].as_array_mut().unwrap() {
                        if c["id"] == "q_boost" {
                            c["mpn"] = "STW65N65DM2".into();
                        }
                    }
                }
                "stackup" => changed["copper_layer_count"] = 8.into(),
                _ => changed["unreviewed_field"] = true.into(),
            }
            assert!(
                reviewed_boost_identity_input(&serde_json::to_vec(&changed).unwrap(), &retained)
                    .is_err(),
                "{mutation}"
            );
        }
        // There is no general waiver for the prior board or an empty transfer.
        let mut changed = original;
        changed["board_file_utf8"] = serde_json::from_slice::<serde_json::Value>(&historical)
            .unwrap()["board_file_utf8"]
            .clone();
        changed["board_sha256"] =
            crate::runner::digest(changed["board_file_utf8"].as_str().unwrap().as_bytes()).into();
        assert!(
            reviewed_boost_identity_input(&serde_json::to_vec(&changed).unwrap(), &retained)
                .is_err()
        );
    }

    #[test]
    fn missing_evidence_and_missing_waveform_cannot_qualify() {
        let missing = run(None, None, b"{}", None);
        assert_eq!(missing.status, Status::Indeterminate);
        assert_eq!(missing.checked_rules.len(), 3);
        assert_eq!(
            run(Some(Path::new("absent")), None, b"{}", None).status,
            Status::Fail
        );
    }
    #[test]
    fn retained_assembly_replay_passes_numerics_without_qualifying_hardware() {
        let root = Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
        let candidate = root.join("power-entry/shunt-repair");
        let source =
            std::fs::read_to_string(candidate.join("candidate/source-manifest.json")).unwrap();
        let native = std::fs::read_to_string(candidate.join("evidence/native-04.json")).unwrap();
        let board = std::fs::read_to_string(candidate.join("candidate/section.kicad_pcb")).unwrap();
        let manufacturing = serde_json::from_slice(
            &std::fs::read(root.join("power-entry/shunt-repair/evidence/manufacturing-04.json"))
                .unwrap(),
        )
        .unwrap();
        let pfc = crate::pfc_power::run(&source, &native, &board, &manufacturing).unwrap();
        let report = run(
            None,
            Some(&root.join("power-entry/shunt-assembly/run-15")),
            native.as_bytes(),
            Some(&pfc),
        );
        assert_eq!(report.status, Status::Indeterminate, "{report:?}");
        assert_eq!(
            report
                .findings
                .iter()
                .find(|f| f.rule == RULES[2])
                .unwrap()
                .status,
            Status::Pass,
            "{report:?}"
        );
        assert_eq!(
            report
                .findings
                .iter()
                .find(|f| f.rule == RULES[1])
                .unwrap()
                .status,
            Status::Indeterminate
        );
    }
}
