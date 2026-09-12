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
    /// Native copper layer. Coupling is evaluated only for traces on the
    /// same physical layer; a layer mismatch is not silently flattened.
    pub layer: String,
    pub width_mm: f64,
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
    pub max_parallel_mm: Option<f64>,
    /// Maximum same-layer gap at which parallel overlap is considered
    /// coupled. This is a geometric screen, not an EMC or inductance limit.
    pub max_spacing_mm: Option<f64>,
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

fn parallel_overlap(
    aggressors: &[&SwitchingTrace],
    victims: &[&SwitchingTrace],
    max_spacing_mm: Option<f64>,
) -> f64 {
    // Measure covered length along each aggressor segment. Victim projections
    // are unioned in that segment's own coordinate system; directions and
    // separate layers must never be mixed into a global projection.
    // Coincident duplicate aggressor copper is conservatively counted twice.
    let mut total = 0.0;
    for a in aggressors {
        for ap in a.points_mm.windows(2) {
            let (ax, ay) = (ap[1][0] - ap[0][0], ap[1][1] - ap[0][1]);
            let al = ax.hypot(ay);
            if !al.is_finite() || al == 0.0 {
                continue;
            }
            let mut intervals = Vec::new();
            for v in victims.iter().filter(|v| v.layer == a.layer) {
                for vp in v.points_mm.windows(2) {
                    let (vx, vy) = (vp[1][0] - vp[0][0], vp[1][1] - vp[0][1]);
                    let vl = vx.hypot(vy);
                    if !vl.is_finite() || vl == 0.0 {
                        continue;
                    }
                    let cross = (ax * vy - ay * vx).abs() / (al * vl);
                    if cross > 1e-9 {
                        continue;
                    }
                    let center_distance =
                        ((vp[0][0] - ap[0][0]) * ay - (vp[0][1] - ap[0][1]) * ax).abs() / al;
                    let edge_gap = center_distance - (a.width_mm + v.width_mm) / 2.0;
                    if !edge_gap.is_finite() || max_spacing_mm.is_some_and(|s| edge_gap > s) {
                        continue;
                    }
                    let ux = ax / al;
                    let uy = ay / al;
                    let project = |p: [f64; 2]| (p[0] - ap[0][0]) * ux + (p[1] - ap[0][1]) * uy;
                    let b0 = project(vp[0]);
                    let b1 = project(vp[1]);
                    let start = b0.min(b1).max(0.0);
                    let end = b0.max(b1).min(al);
                    if end > start {
                        intervals.push((start, end));
                    }
                }
            }
            intervals.sort_by(|a, b| a.0.total_cmp(&b.0));
            let mut covered_until = 0.0_f64;
            for (start, end) in intervals {
                total += (end - start.max(covered_until)).max(0.0);
                covered_until = covered_until.max(end);
            }
        }
    }
    total
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
        if trace.layer.trim().is_empty()
            || trace.points_mm.len() < 2
            || trace.points_mm.windows(2).any(|p| p[0] == p[1])
            || !trace.width_mm.is_finite()
            || trace.width_mm <= 0.0
            || trace
                .points_mm
                .iter()
                .any(|p| !p[0].is_finite() || !p[1].is_finite())
        {
            findings.push(Finding::fail(
                NOISE_RULE,
                "native trace layer, positive width, and finite points are required",
                trace.id.clone(),
            ));
        }
    }
    if !findings.is_empty() {
        return CheckReport::from_findings(
            findings,
            checked,
            vec!["malformed native trace geometry prevents switching evaluation".into()],
        );
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
        if pair.aggressor_net == pair.victim_net {
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
        let overlap = parallel_overlap(a, v, pair.max_spacing_mm);
        let malformed = pair
            .max_parallel_mm
            .is_some_and(|v| !v.is_finite() || v <= 0.0)
            || pair
                .max_spacing_mm
                .is_some_and(|v| !v.is_finite() || v < 0.0);
        if malformed {
            findings.push(Finding::fail(
                NOISE_RULE,
                "authored spacing/overlap limits must be finite, with nonnegative spacing and positive overlap bound",
                format!("{} -> {}", pair.aggressor_net, pair.victim_net),
            ));
        } else if let (Some(limit), Some(_)) = (pair.max_parallel_mm, pair.max_spacing_mm) {
            if overlap > limit {
                findings.push(Finding::fail(
                    NOISE_RULE,
                    format!("same-layer parallel overlap {overlap:.3} mm exceeds {limit:.3} mm"),
                    format!("{} -> {}", pair.aggressor_net, pair.victim_net),
                ));
            } else {
                findings.push(Finding::pass(
                    NOISE_RULE,
                    format!(
                        "same-layer parallel overlap {overlap:.3} mm is within {:.3} mm",
                        limit
                    ),
                    format!("{} -> {}", pair.aggressor_net, pair.victim_net),
                ));
            }
        } else {
            findings.push(Finding::indeterminate(NOISE_RULE,
                format!("measured same-layer parallel overlap {overlap:.3} mm; authored spacing/overlap limits are required"),
                format!("{} -> {}", pair.aggressor_net, pair.victim_net)));
        }
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
                        layer: "F.Cu".into(),
                        width_mm: 0.3,
                        points_mm: vec![[0.0, 0.0], [4.0, 0.0]],
                    },
                    SwitchingTrace {
                        id: "ret".into(),
                        net: "PGND".into(),
                        layer: "F.Cu".into(),
                        width_mm: 0.3,
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
                    max_parallel_mm: Some(5.0),
                    max_spacing_mm: Some(0.5),
                }],
            },
        )
    }
    #[test]
    fn baseline_passes() {
        assert_eq!(
            validate(&baseline().0, &baseline().1).status,
            zapote_core::Status::Pass
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

    #[test]
    fn parallel_overlap_fails_only_when_same_layer_and_close() {
        let (mut b, mut c) = baseline();
        b.traces.push(SwitchingTrace {
            id: "victim".into(),
            net: "V".into(),
            layer: "F.Cu".into(),
            width_mm: 0.3,
            points_mm: vec![[0.0, 0.2], [4.0, 0.2]],
        });
        c.noise_pairs = vec![NoisePair {
            aggressor_net: "SW".into(),
            victim_net: "V".into(),
            max_parallel_mm: Some(2.0),
            max_spacing_mm: Some(0.5),
        }];
        assert_eq!(validate(&b, &c).status, zapote_core::Status::Fail);
        c.noise_pairs[0].max_parallel_mm = Some(5.0);
        assert_eq!(validate(&b, &c).status, zapote_core::Status::Pass);
    }

    #[test]
    fn perpendicular_remote_and_different_layer_do_not_count_as_parallel() {
        let (mut b, mut c) = baseline();
        b.traces.push(SwitchingTrace {
            id: "victim".into(),
            net: "V".into(),
            layer: "B.Cu".into(),
            width_mm: 0.3,
            points_mm: vec![[0.0, 0.2], [0.0, 4.2]],
        });
        c.noise_pairs = vec![NoisePair {
            aggressor_net: "SW".into(),
            victim_net: "V".into(),
            max_parallel_mm: Some(0.001),
            max_spacing_mm: Some(0.5),
        }];
        // max_parallel=0 is invalid as a contract, so use a tiny positive
        // bound while still proving no same-layer parallel overlap.
        assert_eq!(validate(&b, &c).status, zapote_core::Status::Pass);
    }

    #[test]
    fn splitting_native_traces_preserves_measured_overlap() {
        let (mut b, mut c) = baseline();
        b.traces[1].points_mm = vec![[0.0, 0.5], [4.0, 0.5]];
        c.noise_pairs[0].max_parallel_mm = Some(3.0);
        assert_eq!(validate(&b, &c).status, zapote_core::Status::Fail);
        let mut split = b.traces[0].clone();
        split.id = "second-half".into();
        split.points_mm = vec![[2.0, 0.0], [4.0, 0.0]];
        b.traces[0].points_mm = vec![[0.0, 0.0], [2.0, 0.0]];
        b.traces.push(split);
        assert_eq!(validate(&b, &c).status, zapote_core::Status::Fail);
        let a: Vec<_> = b.traces.iter().filter(|t| t.net == "SW").collect();
        assert_eq!(parallel_overlap(&a, &[&b.traces[1]], Some(0.5)), 4.0);
    }

    #[test]
    fn projection_axes_and_duplicate_victims_do_not_manufacture_overlap() {
        let (b, _) = baseline();
        let a = &b.traces[0];
        let mut v = b.traces[1].clone();
        v.points_mm = vec![[0.0, 0.5], [2.0, 0.5], [2.0, 4.0]];
        assert_eq!(parallel_overlap(&[a], &[&v, &v], Some(0.5)), 2.0);
        v.points_mm = vec![[0.0, 5.0], [4.0, 5.0]];
        assert_eq!(parallel_overlap(&[a], &[&v], Some(0.5)), 0.0);
        v.points_mm = vec![[2.0, -2.0], [2.0, 2.0]];
        assert_eq!(parallel_overlap(&[a], &[&v], Some(0.5)), 0.0);
        v.points_mm = vec![[4.0, 0.5], [0.0, 0.5]];
        assert_eq!(parallel_overlap(&[a], &[&v], Some(0.5)), 4.0);
    }

    #[test]
    fn missing_spacing_and_malformed_limits_cannot_pass() {
        let (mut b, mut c) = baseline();
        c.noise_pairs[0].max_spacing_mm = None;
        assert_eq!(validate(&b, &c).status, zapote_core::Status::Indeterminate);
        c.noise_pairs[0].max_spacing_mm = Some(f64::NAN);
        assert_eq!(validate(&b, &c).status, zapote_core::Status::Fail);
        c.noise_pairs[0].max_spacing_mm = Some(0.5);
        b.traces[0].points_mm.clear();
        assert_eq!(validate(&b, &c).status, zapote_core::Status::Fail);
    }
}
