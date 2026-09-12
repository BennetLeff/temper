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
            current_endpoints: vec!["driver.14".into(), "gate_h.1".into()],
            return_endpoint: "driver.1".into(),
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
        assert_eq!(report.status, zapote_core::Status::Indeterminate);
        let mut enlarged = board.clone();
        enlarged.traces[0].points_mm.push([100.0, 100.0]);
        let mut bounded = contract.clone();
        bounded.paths[0].max_bbox_area_mm2 = Some(10.0);
        assert_eq!(
            zapote_drc::switching::validate(&enlarged, &bounded).status,
            zapote_core::Status::Fail
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
    fn four_saved_units_report_measured_geometry_and_missing_limits() {
        let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR"));
        for (unit, dir, native_name) in [
            ("gate-drive", "gate-drive", "native-09.json"),
            ("power-entry", "power-entry", "native-11.json"),
            ("current-sense", "current-sense", "native-final.json"),
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
                        .any(|f| f.rule == "DRC.P3.SOURCE_BINDING"),
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
    if !embedded_matches && !hashed_matches {
        return Err("native export does not identify supplied saved board bytes".into());
    }
    let evidence: UnitNativeEvidence =
        serde_json::from_str(native).map_err(|e| format!("native evidence: {e}"))?;
    let board = SwitchingBoard {
        traces: evidence
            .traces
            .into_iter()
            .map(|t| SwitchingTrace {
                id: t.id,
                net: t.net,
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
        return_connectivity_evidence: evidence
            .connectivity_clusters
            .iter()
            .map(|c| c.net.clone())
            .collect(),
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

fn append(dst: &mut zapote_core::CheckReport, src: zapote_core::CheckReport) {
    dst.findings.extend(src.findings);
    dst.checked_rules.extend(src.checked_rules);
    dst.coverage_gaps.extend(src.coverage_gaps);
    dst.status = if dst
        .findings
        .iter()
        .any(|f| f.status == zapote_core::Status::Fail)
    {
        zapote_core::Status::Fail
    } else if dst
        .findings
        .iter()
        .any(|f| f.status == zapote_core::Status::Indeterminate)
        || !dst.coverage_gaps.is_empty()
    {
        zapote_core::Status::Indeterminate
    } else {
        zapote_core::Status::Pass
    };
}

/// Run the P3 subset against one saved unit. Net names are an explicit
/// source-contract table; endpoint membership is resolved from `Circuit` and
/// native binding is required before geometry is evaluated.
pub fn run(unit: &str, source: &str, native: &str, board: &[u8]) -> zapote_core::CheckReport {
    let (entry, current, return_net) = match unit {
        "gate-drive" => (
            zapote_erc::gate_drive::ENTRY,
            vec!["gate_h_out"],
            "ctrl_gnd",
        ),
        "pfc" | "power-entry" => (zapote_erc::power_entry::ENTRY, vec!["q_boost-g"], "minus"),
        "current-sense" => (
            "elec/src/current_sense_unit.ato:CurrentSenseUnit",
            vec!["PRIMARY_IN", "PRIMARY_OUT"],
            "gnd",
        ),
        "interlock" => {
            return zapote_core::CheckReport::from_findings(
                vec![zapote_core::Finding::indeterminate(
                    "DRC.P3.APPLICABILITY",
                    "interlock is a shutdown/control unit; commutation geometry is not applicable",
                    unit,
                )],
                vec!["DRC.P3.APPLICABILITY".into()],
                vec!["interlock switching loop out of scope".into()],
            )
        }
        _ => {
            return zapote_core::CheckReport::from_findings(
                vec![zapote_core::Finding::indeterminate(
                    "DRC.P3.APPLICABILITY",
                    "unknown P3 unit",
                    unit,
                )],
                vec!["DRC.P3.APPLICABILITY".into()],
                vec![],
            )
        }
    };
    let circuit = match zapote_erc::source_circuit::Circuit::parse(source, entry) {
        Ok(c) => c,
        Err(e) => {
            return zapote_core::CheckReport::from_findings(
                vec![zapote_core::Finding::indeterminate(
                    "DRC.P3.SOURCE_BINDING",
                    e,
                    unit,
                )],
                vec!["DRC.P3.SOURCE_BINDING".into()],
                vec![],
            )
        }
    };
    let endpoint_for = |net: &str| {
        circuit
            .pins
            .iter()
            .find(|(_, value)| value.as_str() == net)
            .map(|(endpoint, _)| endpoint.clone())
    };
    let Some(return_endpoint) = endpoint_for(return_net) else {
        return zapote_core::CheckReport::from_findings(
            vec![zapote_core::Finding::indeterminate(
                "DRC.P3.SOURCE_BINDING",
                format!("source return net {return_net} has no endpoint"),
                unit,
            )],
            vec!["DRC.P3.SOURCE_BINDING".into()],
            vec![],
        );
    };
    let Some(current_endpoints) = current
        .iter()
        .map(|net| endpoint_for(net))
        .collect::<Option<Vec<_>>>()
    else {
        return zapote_core::CheckReport::from_findings(
            vec![zapote_core::Finding::indeterminate(
                "DRC.P3.SOURCE_BINDING",
                "one or more explicit switching nets have no source endpoint",
                unit,
            )],
            vec!["DRC.P3.SOURCE_BINDING".into()],
            vec![],
        );
    };
    let path = SourcePath {
        name: format!("{unit}_commutation"),
        current_endpoints,
        return_endpoint,
        max_bbox_area_mm2: None,
        required_return_stitches: None,
    };
    let mut report = zapote_core::CheckReport::from_findings(vec![], vec![], vec![]);
    match switching_input(source, entry, native, board, &[path], vec![]) {
        Ok((geometry, contract)) => append(
            &mut report,
            zapote_drc::switching::validate(&geometry, &contract),
        ),
        Err(e) => report.findings.push(zapote_core::Finding::fail(
            "DRC.P3.SOURCE_NATIVE_BINDING",
            e,
            unit,
        )),
    }
    append(
        &mut report,
        zapote_erc::operating_limits::validate(None, None),
    );
    report
}
