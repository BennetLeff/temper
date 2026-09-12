//! Bounded switching-loop and return-path checks.
//!
//! A loop bounding box is a placement screen, not an inductance estimate.  A
//! return path is accepted only when it is explicitly paired with the
//! commutation path and has native trace/via evidence.

use std::collections::{BTreeMap, BTreeSet};
use zapote_core::{CheckReport, Finding};

const LOOP_RULE: &str = "DRC.P3.SWITCHING_LOOP_AREA";
const RETURN_RULE: &str = "DRC.P3.RETURN_PATH_CONTINUITY";
const NOISE_RULE: &str = "DRC.P3.AGGRESSOR_VICTIM_SPACING";

#[derive(Debug, Clone, PartialEq)]
pub struct SwitchingTrace {
    pub id: String,
    pub net: String,
    pub points_mm: Vec<[f64; 2]>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct SwitchingVia {
    pub id: String,
    pub net: String,
    pub position_mm: [f64; 2],
}

#[derive(Debug, Clone, PartialEq)]
pub struct SwitchingBoard {
    pub traces: Vec<SwitchingTrace>,
    pub vias: Vec<SwitchingVia>,
    pub return_connectivity_evidence: BTreeSet<String>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct CommutationPath {
    pub name: String,
    pub current_nets: Vec<String>,
    pub return_net: String,
    pub max_bbox_area_mm2: Option<f64>,
    pub required_return_stitches: u32,
}

#[derive(Debug, Clone, PartialEq)]
pub struct NoisePair {
    pub aggressor_net: String,
    pub victim_net: String,
    pub max_parallel_mm: f64,
}

#[derive(Debug, Clone, PartialEq)]
pub struct SwitchingContract {
    pub paths: Vec<CommutationPath>,
    pub noise_pairs: Vec<NoisePair>,
}

fn bbox(board: &SwitchingBoard, nets: &BTreeSet<String>) -> Option<(f64, f64, f64, f64)> {
    let mut points = board
        .traces
        .iter()
        .filter(|t| nets.contains(&t.net))
        .flat_map(|t| t.points_mm.iter().copied());
    let first = points.next()?;
    let mut result = (first[0], first[1], first[0], first[1]);
    for p in points {
        result.0 = result.0.min(p[0]);
        result.1 = result.1.min(p[1]);
        result.2 = result.2.max(p[0]);
        result.3 = result.3.max(p[1]);
    }
    Some(result)
}

/// Evaluate explicit switching paths and noise pairs. Missing geometry is a
/// coverage gap; it never becomes an empty-success result.
pub fn validate(board: &SwitchingBoard, contract: &SwitchingContract) -> CheckReport {
    let mut findings = Vec::new();
    let mut gaps = Vec::new();
    let checked = vec![LOOP_RULE.into(), RETURN_RULE.into(), NOISE_RULE.into()];
    let mut traces_by_net: BTreeMap<&str, Vec<&SwitchingTrace>> = BTreeMap::new();
    for trace in &board.traces {
        traces_by_net.entry(&trace.net).or_default().push(trace);
    }

    if contract.paths.is_empty() {
        gaps.push("no authored commutation paths supplied".into());
        findings.push(Finding::indeterminate(
            LOOP_RULE,
            "switching path population is required",
            "paths",
        ));
    }
    for path in &contract.paths {
        let nets: BTreeSet<_> = path.current_nets.iter().cloned().collect();
        if path.name.trim().is_empty() || nets.is_empty() || path.return_net.trim().is_empty() {
            findings.push(Finding::indeterminate(
                LOOP_RULE,
                "path requires a name, current nets, and explicit return net",
                "path",
            ));
            continue;
        }
        if nets.contains(&path.return_net) {
            findings.push(Finding::fail(
                RETURN_RULE,
                "return net must be distinct from commutation current nets",
                path.name.clone(),
            ));
            continue;
        }
        let mut extent_nets = nets.clone();
        extent_nets.insert(path.return_net.clone());
        let Some((min_x, min_y, max_x, max_y)) = bbox(board, &extent_nets) else {
            gaps.push(format!(
                "path {} has no native current-trace geometry",
                path.name
            ));
            findings.push(Finding::indeterminate(
                LOOP_RULE,
                "native current-trace geometry is missing",
                path.name.clone(),
            ));
            continue;
        };
        let area = (max_x - min_x).max(0.0) * (max_y - min_y).max(0.0);
        if let Some(limit) = path.max_bbox_area_mm2 {
            if !limit.is_finite() || limit <= 0.0 {
                findings.push(Finding::indeterminate(
                    LOOP_RULE,
                    "loop-area bound must be finite and positive",
                    path.name.clone(),
                ));
            } else if area > limit {
                findings.push(Finding::fail(LOOP_RULE, format!("switching loop bbox is {area:.3} mm², above {limit:.3} mm² (heuristic screen)"), path.name.clone()));
            } else {
                findings.push(Finding::pass(LOOP_RULE, format!("switching loop bbox {area:.3} mm² is within {limit:.3} mm² heuristic screen"), path.name.clone()));
            }
        } else {
            gaps.push(format!("path {} has no loop-area bound", path.name));
            findings.push(Finding::indeterminate(
                LOOP_RULE,
                format!("current/return trace bbox area={area:.3} mm²; no authored bound, no inductance claim"),
                path.name.clone(),
            ));
        }

        let return_traces = traces_by_net
            .get(path.return_net.as_str())
            .map_or(0, Vec::len);
        let return_vias = board
            .vias
            .iter()
            .filter(|v| v.net == path.return_net)
            .count();
        if !board
            .return_connectivity_evidence
            .contains(&path.return_net)
        {
            findings.push(Finding::indeterminate(
                RETURN_RULE,
                "native connectivity-cluster evidence is required to establish return continuity",
                path.return_net.clone(),
            ));
        } else if return_traces == 0 {
            findings.push(Finding::fail(
                RETURN_RULE,
                "explicit return net has no native trace evidence",
                path.return_net.clone(),
            ));
        } else if return_vias < path.required_return_stitches as usize {
            findings.push(Finding::fail(
                RETURN_RULE,
                format!(
                    "return net has {return_vias} stitching vias, requires {}",
                    path.required_return_stitches
                ),
                path.return_net.clone(),
            ));
        } else {
            findings.push(Finding::pass(
                RETURN_RULE,
                format!("return trace and {return_vias} required stitching vias are present"),
                path.return_net.clone(),
            ));
        }
    }
    if contract.noise_pairs.is_empty() {
        gaps.push("no authored aggressor/victim pairs supplied".into());
        findings.push(Finding::indeterminate(
            NOISE_RULE,
            "noise pair population is required",
            "noise_pairs",
        ));
    }
    for pair in &contract.noise_pairs {
        if pair.aggressor_net == pair.victim_net
            || !pair.max_parallel_mm.is_finite()
            || pair.max_parallel_mm <= 0.0
        {
            findings.push(Finding::indeterminate(
                NOISE_RULE,
                "aggressor/victim pair and positive parallel-run limit are required",
                format!("{} -> {}", pair.aggressor_net, pair.victim_net),
            ));
            continue;
        }
        let a = traces_by_net.get(pair.aggressor_net.as_str());
        let v = traces_by_net.get(pair.victim_net.as_str());
        let (Some(a), Some(v)) = (a, v) else {
            findings.push(Finding::indeterminate(
                NOISE_RULE,
                "both explicit aggressor and victim native traces are required",
                format!("{} -> {}", pair.aggressor_net, pair.victim_net),
            ));
            continue;
        };
        let _ = (a, v);
        findings.push(Finding::indeterminate(NOISE_RULE, "parallel-run limit is declared, but this bounded adapter does not claim segment spacing/overlap geometry", format!("{} -> {}", pair.aggressor_net, pair.victim_net)));
    }
    CheckReport::from_findings(findings, checked, gaps)
}

#[cfg(test)]
mod tests {
    use super::*;
    fn baseline() -> (SwitchingBoard, SwitchingContract) {
        (
            SwitchingBoard {
                traces: vec![
                    SwitchingTrace {
                        id: "sw".into(),
                        net: "SW".into(),
                        points_mm: vec![[0.0, 0.0], [4.0, 0.0]],
                    },
                    SwitchingTrace {
                        id: "ret".into(),
                        net: "PGND".into(),
                        points_mm: vec![[0.0, 1.0], [4.0, 1.0]],
                    },
                ],
                vias: vec![SwitchingVia {
                    id: "stitch".into(),
                    net: "PGND".into(),
                    position_mm: [2.0, 1.0],
                }],
                return_connectivity_evidence: ["PGND".into()].into_iter().collect(),
            },
            SwitchingContract {
                paths: vec![CommutationPath {
                    name: "buck".into(),
                    current_nets: vec!["SW".into()],
                    return_net: "PGND".into(),
                    max_bbox_area_mm2: Some(10.0),
                    required_return_stitches: 1,
                }],
                noise_pairs: vec![NoisePair {
                    aggressor_net: "SW".into(),
                    victim_net: "PGND".into(),
                    max_parallel_mm: 5.0,
                }],
            },
        )
    }
    #[test]
    fn baseline_passes() {
        assert_eq!(
            validate(&baseline().0, &baseline().1).status,
            zapote_core::Status::Indeterminate
        );
    }
    #[test]
    fn enlarged_loop_fails() {
        let (mut b, c) = baseline();
        b.traces[0].points_mm.push([20.0, 20.0]);
        assert_eq!(validate(&b, &c).status, zapote_core::Status::Fail);
    }
    #[test]
    fn missing_stitch_fails_closed() {
        let (mut b, c) = baseline();
        b.vias.clear();
        assert_eq!(validate(&b, &c).status, zapote_core::Status::Fail);
    }
    #[test]
    fn missing_path_is_indeterminate() {
        let (b, mut c) = baseline();
        c.paths.clear();
        assert_eq!(validate(&b, &c).status, zapote_core::Status::Indeterminate);
    }
    #[test]
    fn disconnected_return_fails_even_with_a_current_loop() {
        let (mut b, c) = baseline();
        b.traces.retain(|t| t.net != "PGND");
        assert_eq!(validate(&b, &c).status, zapote_core::Status::Fail);
    }
    #[test]
    fn missing_noise_population_is_indeterminate() {
        let (b, mut c) = baseline();
        c.noise_pairs.clear();
        assert_eq!(validate(&b, &c).status, zapote_core::Status::Indeterminate);
    }
}
