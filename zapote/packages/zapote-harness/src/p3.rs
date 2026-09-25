//! P3 adapter from retained native exports and compiled source graphs.
//! The adapter performs no classification by name: every path is a reviewed
//! list of exact source endpoints supplied by the caller.

use sha2::Digest;
use zapote_core::unit::UnitNativeEvidence;
use zapote_drc::switching::{
    CommutationPath, NoisePair, SwitchingBoard, SwitchingContract, SwitchingTrace, SwitchingVia,
};
use zapote_erc::source_circuit::Circuit;

#[derive(Debug, Clone)]
pub struct SourcePath {
    pub name: String,
    pub current_endpoints: Vec<String>,
    pub return_endpoint: String,
    pub max_bbox_area_mm2: Option<f64>,
    pub required_return_stitches: Option<u32>,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn gate_drive_saved_native_export_binds_reviewed_paths() {
        let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR"));
        let source =
            std::fs::read_to_string(root.join("../../gate-drive/candidate/source-manifest.json"))
                .unwrap();
        let native =
            std::fs::read_to_string(root.join("../../gate-drive/evidence/native-09.json")).unwrap();
        let paths = [SourcePath {
            name: "gate_h_commutation".into(),
            current_endpoints: vec!["driver.15".into(), "gate_h.1".into()],
            return_endpoint: "driver.14".into(),
            max_bbox_area_mm2: None,
            required_return_stitches: None,
        }];
        let board_bytes = serde_json::from_str::<serde_json::Value>(&native).unwrap()
            ["board_file_utf8"]
            .as_str()
            .unwrap()
            .as_bytes()
            .to_vec();
        let (board, contract) = switching_input(
            &source,
            zapote_erc::gate_drive::ENTRY,
            &native,
            &board_bytes,
            &paths,
            vec![],
        )
        .unwrap();
        let report = zapote_drc::switching::validate(&board, &contract);
        println!(
            "gate-drive P3 status: {:?}; traces={}, vias={}, findings={}, gaps={}",
            report.status,
            board.traces.len(),
            board.vias.len(),
            report.findings.len(),
            report.coverage_gaps.len()
        );
        assert!(!report.checked_rules.is_empty());
        assert!(report
            .findings
            .iter()
            .any(|f| f.rule == "DRC.P3.SWITCHING_LOOP_AREA"));
        assert!(report
            .findings
            .iter()
            .any(|f| f.rule == "DRC.P3.AGGRESSOR_VICTIM_SPACING"));
        assert_eq!(report.status, zapote_core::Status::Indeterminate);
        let mut enlarged = board.clone();
        enlarged.traces[0].points_mm.push([100.0, 100.0]);
        let mut bounded = contract.clone();
        bounded.paths[0].max_bbox_area_mm2 = Some(10.0);
        assert_eq!(
            zapote_drc::switching::validate(&enlarged, &bounded).status,
            zapote_core::Status::Indeterminate
        );
        let mut disconnected = board;
        let return_net = contract.paths[0].return_net.clone();
        disconnected.traces.retain(|t| t.net != return_net);
        assert_eq!(
            zapote_drc::switching::validate(&disconnected, &contract).status,
            zapote_core::Status::Fail
        );
    }

    #[test]
    fn actual_gate_noise_measurement_responds_to_native_geometry() {
        let source = include_str!("../../../gate-drive/candidate/source-manifest.json");
        let native = include_str!("../../../gate-drive/evidence/native-09.json");
        let json: serde_json::Value = serde_json::from_str(native).unwrap();
        let circuit = Circuit::parse(source, zapote_erc::gate_drive::ENTRY).unwrap();
        let aggressor = circuit.net("driver.15").unwrap().to_owned();
        let victim = circuit.net("driver.1").unwrap().to_owned();
        let pairs = vec![NoisePair {
            aggressor_net: aggressor.clone(),
            victim_net: victim.clone(),
            max_parallel_mm: Some(0.1),
            max_spacing_mm: Some(0.5),
        }];
        let (mut board, contract) = switching_input(
            source,
            zapote_erc::gate_drive::ENTRY,
            native,
            json["board_file_utf8"].as_str().unwrap().as_bytes(),
            &[],
            pairs,
        )
        .unwrap();
        let original = zapote_drc::switching::validate(&board, &contract);
        assert!(original
            .findings
            .iter()
            .any(|f| f.rule == "DRC.P3.AGGRESSOR_VICTIM_SPACING"
                && f.message.contains("parallel overlap")));
        // Mutate the transported geometry in memory, never the saved PCB.
        let a = board
            .traces
            .iter_mut()
            .find(|t| t.net == aggressor)
            .unwrap();
        a.points_mm = vec![[0., 0.], [100., 0.]];
        a.layer = "F.Cu".into();
        let v = board.traces.iter_mut().find(|t| t.net == victim).unwrap();
        v.points_mm = vec![[0., 0.1], [100., 0.1]];
        v.layer = "F.Cu".into();
        let changed = zapote_drc::switching::validate(&board, &contract);
        let before = original
            .findings
            .iter()
            .find(|f| f.rule == "DRC.P3.AGGRESSOR_VICTIM_SPACING")
            .unwrap();
        let after = changed
            .findings
            .iter()
            .find(|f| f.rule == "DRC.P3.AGGRESSOR_VICTIM_SPACING")
            .unwrap();
        assert_ne!(before.message, after.message);
        assert_eq!(after.status, zapote_core::Status::Fail);
    }

    #[test]
    fn saved_units_report_measured_geometry_and_missing_limits() {
        let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR"));
        for (unit, dir, native_name) in [
            ("gate-drive", "gate-drive", "native-09.json"),
            (
                "current-sense",
                "current-sense",
                "stackup-fix/native-fixed.json",
            ),
            ("interlock", "interlock", "native-final.json"),
        ] {
            let source = std::fs::read_to_string(
                root.join(format!("../../{dir}/candidate/source-manifest.json")),
            )
            .unwrap();
            let native =
                std::fs::read_to_string(root.join(format!("../../{dir}/evidence/{native_name}")))
                    .unwrap();
            let json = serde_json::from_str::<serde_json::Value>(&native).unwrap();
            let board = json["board_file_utf8"].as_str().map_or_else(
                || {
                    std::fs::read(root.join(format!("../../{dir}/candidate/section.kicad_pcb")))
                        .unwrap()
                },
                |v| v.as_bytes().to_vec(),
            );
            let report = run(unit, &source, &native, &board);
            if unit == "current-sense" || unit == "interlock" {
                assert!(
                    report
                        .findings
                        .iter()
                        .any(|f| f.rule == "DRC.P3.APPLICABILITY"),
                    "{unit}: {report:?}"
                );
                continue;
            }
            assert!(
                report
                    .checked_rules
                    .iter()
                    .any(|r| r == "DRC.P3.SWITCHING_LOOP_AREA"),
                "{unit}: {report:?}"
            );
            assert!(
                report
                    .findings
                    .iter()
                    .any(|f| f.rule == "DRC.P3.AGGRESSOR_VICTIM_SPACING"),
                "{unit}: noise geometry was not evaluated: {report:?}"
            );
            assert!(report
                .findings
                .iter()
                .any(|f| f.rule == "ERC.P3.THERMAL_OPERATING_LIMIT"));
        }
    }
}

/// Bind exact source endpoint names to native geometry and construct the P3
/// input. A missing endpoint is an adapter error, never an empty population.
pub fn switching_input(
    source: &str,
    entry: &str,
    native: &str,
    board_bytes: &[u8],
    paths: &[SourcePath],
    noise_pairs: Vec<NoisePair>,
) -> Result<(SwitchingBoard, SwitchingContract), String> {
    let circuit = Circuit::parse(source, entry)?;
    circuit.bind_native(native)?;
    let native_json: serde_json::Value =
        serde_json::from_str(native).map_err(|e| format!("native JSON: {e}"))?;
    let embedded_matches =
        native_json["board_file_utf8"].as_str().map(str::as_bytes) == Some(board_bytes);
    let hashed_matches = native_json["board_sha256"].as_str()
        == Some(&format!("{:x}", sha2::Sha256::digest(board_bytes)));
    if !embedded_matches || !hashed_matches {
        return Err("native export does not identify supplied saved board bytes".into());
    }
    let evidence: UnitNativeEvidence =
        serde_json::from_str(native).map_err(|e| format!("native evidence: {e}"))?;
    let connected: std::collections::BTreeSet<String> = evidence
        .connectivity_clusters
        .iter()
        .filter(|cluster| {
            !cluster.nodes.is_empty()
                && evidence
                    .connectivity_clusters
                    .iter()
                    .filter(|c| c.net == cluster.net)
                    .count()
                    == 1
                && cluster
                    .nodes
                    .iter()
                    .cloned()
                    .collect::<std::collections::BTreeSet<_>>()
                    == evidence
                        .connections
                        .iter()
                        .filter(|c| c.net == cluster.net)
                        .map(|c| format!("{}.{}", c.component, c.pin))
                        .collect()
        })
        .map(|c| c.net.clone())
        .collect();
    let board = SwitchingBoard {
        traces: evidence
            .traces
            .into_iter()
            .map(|t| SwitchingTrace {
                id: t.id,
                net: t.net,
                layer: t.layer,
                width_mm: t.width_mm,
                points_mm: t.points_mm,
            })
            .collect(),
        vias: evidence
            .vias
            .into_iter()
            .map(|v| SwitchingVia {
                id: v.id,
                net: v.net,
                position_mm: v.position_mm,
            })
            .collect(),
        return_connectivity_evidence: connected,
    };
    let mut bound = Vec::with_capacity(paths.len());
    for path in paths {
        let current_nets = path
            .current_endpoints
            .iter()
            .map(|endpoint| circuit.net(endpoint).map(str::to_owned))
            .collect::<Result<Vec<_>, _>>()?;
        let return_net = circuit.net(&path.return_endpoint)?.to_owned();
        bound.push(CommutationPath {
            name: path.name.clone(),
            current_endpoints: path.current_endpoints.clone(),
            return_endpoint: path.return_endpoint.clone(),
            current_nets,
            return_net,
            max_bbox_area_mm2: path.max_bbox_area_mm2,
            required_return_stitches: path.required_return_stitches.unwrap_or(0),
        });
    }
    Ok((
        board,
        SwitchingContract {
            paths: bound,
            noise_pairs,
        },
    ))
}

/// Run the P3 subset against one saved unit. Net names are an explicit
/// source-contract table; endpoint membership is resolved from `Circuit` and
/// native binding is required before geometry is evaluated.
pub fn run(unit: &str, source: &str, native: &str, board: &[u8]) -> zapote_core::CheckReport {
    use zapote_core::{CheckReport, Finding};
    let operating = zapote_erc::operating_limits::validate(None, None);
    if ["current-sense", "interlock"].contains(&unit) {
        // These units carry sensing / shutdown logic; neither contains a power
        // switch commutation loop. Their actual source/native contract runs in P0.
        return crate::runner::combine(&[&operating, &CheckReport::from_findings(
            vec![Finding::pass("DRC.P3.APPLICABILITY", "no on-board power-switch commutation loop; operating/timing checks remain required", unit)],
            vec!["DRC.P3.APPLICABILITY".into()], vec![])]);
    }
    let (entry, paths) = match unit {
        "gate-drive" => (
            zapote_erc::gate_drive::ENTRY,
            vec![
                SourcePath {
                    name: "high-side gate drive".into(),
                    current_endpoints: vec!["driver.15".into(), "gate_h.1".into()],
                    return_endpoint: "driver.14".into(),
                    max_bbox_area_mm2: None,
                    required_return_stitches: None,
                },
                SourcePath {
                    name: "low-side gate drive".into(),
                    current_endpoints: vec!["driver.10".into(), "gate_l.1".into()],
                    return_endpoint: "driver.9".into(),
                    max_bbox_area_mm2: None,
                    required_return_stitches: None,
                },
            ],
        ),
        _ => {
            return CheckReport::from_findings(
                vec![Finding::fail(
                    "DRC.P3.APPLICABILITY",
                    "unregistered P3 unit",
                    unit,
                )],
                vec!["DRC.P3.APPLICABILITY".into()],
                vec![],
            )
        }
    };
    // Reviewed signal endpoints, separate from the intentional Kelvin returns.
    // These candidates screen switching outputs against control/sense inputs.
    let endpoint_pairs: &[(&str, &str)] = match unit {
        "gate-drive" => &[
            ("driver.15", "driver.1"),
            ("driver.10", "driver.2"),
            ("gate_h.1", "driver.5"),
            ("gate_l.1", "driver.5"),
        ],
        _ => &[],
    };
    let noise_pairs = Circuit::parse(source, entry).and_then(|circuit| {
        endpoint_pairs
            .iter()
            .map(|(a, v)| {
                Ok(NoisePair {
                    aggressor_net: circuit.net(a)?.to_owned(),
                    victim_net: circuit.net(v)?.to_owned(),
                    max_parallel_mm: None,
                    max_spacing_mm: None,
                })
            })
            .collect::<Result<Vec<_>, String>>()
    });
    let noise_pairs = match noise_pairs {
        Ok(pairs) => pairs,
        Err(error) => {
            return crate::runner::combine(&[
                &operating,
                &CheckReport::from_findings(
                    vec![Finding::fail("DRC.P3.SOURCE_NATIVE_BINDING", error, unit)],
                    vec!["DRC.P3.SOURCE_NATIVE_BINDING".into()],
                    vec![],
                ),
            ])
        }
    };
    let geometry = match switching_input(source, entry, native, board, &paths, noise_pairs) {
        Ok((geometry, contract)) => zapote_drc::switching::validate(&geometry, &contract),
        Err(e) => CheckReport::from_findings(
            vec![Finding::fail("DRC.P3.SOURCE_NATIVE_BINDING", e, unit)],
            vec!["DRC.P3.SOURCE_NATIVE_BINDING".into()],
            vec![],
        ),
    };
    crate::runner::combine(&[&geometry, &operating])
}

#[cfg(test)]
mod coordinator_regressions {
    use super::*;
    use zapote_core::Status;

    #[test]
    fn gate_return_is_kelvin_not_control_ground_and_split_cluster_is_incomplete() {
        let source = include_str!("../../../gate-drive/candidate/source-manifest.json");
        let native = include_str!("../../../gate-drive/evidence/native-09.json");
        let board = include_bytes!("../../../gate-drive/candidate/section.kicad_pcb");
        let baseline = run("gate-drive", source, native, board);
        let returns: Vec<_> = baseline
            .findings
            .iter()
            .filter(|f| f.rule == "DRC.P3.RETURN_PATH_CONTINUITY")
            .map(|f| f.object.as_str())
            .collect();
        assert_eq!(returns, vec!["gate_h_kelvin", "gate_l_kelvin"]);
        let mut n: serde_json::Value = serde_json::from_str(native).unwrap();
        let clusters = n["connectivity_clusters"].as_array_mut().unwrap();
        let i = clusters
            .iter()
            .position(|c| c["net"] == "gate_h_kelvin")
            .unwrap();
        let mut split = clusters[i].clone();
        let node = clusters[i]["nodes"].as_array_mut().unwrap().pop().unwrap();
        split["nodes"] = serde_json::json!([node]);
        clusters.push(split);
        let r = run("gate-drive", source, &n.to_string(), board);
        assert!(r
            .findings
            .iter()
            .any(|f| f.rule == "DRC.P3.RETURN_PATH_CONTINUITY"
                && f.object == "gate_h_kelvin"
                && f.status == Status::Indeterminate));
    }
}
