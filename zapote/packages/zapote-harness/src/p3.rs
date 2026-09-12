//! P3 adapter from retained native exports and compiled source graphs.
//! The adapter performs no classification by name: every path is a reviewed
//! list of exact source endpoints supplied by the caller.

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
    pub required_return_stitches: u32,
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
            max_bbox_area_mm2: Some(500.0),
            required_return_stitches: 0,
        }];
        let (board, contract) = switching_input(
            &source,
            zapote_erc::gate_drive::ENTRY,
            &native,
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
    }
}

/// Bind exact source endpoint names to native geometry and construct the P3
/// input. A missing endpoint is an adapter error, never an empty population.
pub fn switching_input(
    source: &str,
    entry: &str,
    native: &str,
    paths: &[SourcePath],
    noise_pairs: Vec<NoisePair>,
) -> Result<(SwitchingBoard, SwitchingContract), String> {
    let circuit = Circuit::parse(source, entry)?;
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
            required_return_stitches: path.required_return_stitches,
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
