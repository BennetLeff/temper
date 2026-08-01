// Routing check: parallel run length between noise-domain net pairs (EMC).
//
// For each NoiseDomain in constraints.noise_domains, checks every emitter ×
// victim net pair: trace segments whose angle differs by ≤ 10° are considered
// parallel. If the distance between parallel segments is < separation * 2
// (where separation is the clearance between the nets' classes), and the
// accumulated parallel run length exceeds max_parallel_run_mm, an ERROR
// violation (EMC_PRL_001) is emitted.
//
// supports_incremental() → true.
// Degenerate cases (0 traces or 0 noise_domains) produce an empty vec.
//
// Origin: U6 of docs/plans/2026-06-30-003-feat-temper-drc-rs-engine-plan.md

use geo::{EuclideanDistance, Line};
use std::collections::HashMap;
use std::f64::consts::PI;

use crate::board::BoardState;
use crate::constraints::ConstraintSet;
use crate::rules::{clearance_between, violation, DrcCategory, DrcRule, Severity, Violation};

/// Angle tolerance for considering two segments "parallel" (radians).
const PARALLEL_ANGLE_TOLERANCE_RAD: f64 = 10.0 * PI / 180.0; // 10°

/// Default separation clearance (mm) when net class is unknown.
const DEFAULT_SEPARATION_MM: f64 = 0.2;

#[derive(Default)]
pub struct ParallelRunCheck;

impl ParallelRunCheck {
    pub fn new() -> Self {
        Self
    }
}

impl DrcRule for ParallelRunCheck {
    fn name(&self) -> &str {
        "routing_parallel_run"
    }

    fn category(&self) -> DrcCategory {
        DrcCategory::Emc
    }

    fn description(&self) -> &str {
        "Check parallel run length between coupled net pairs in noise domains (EMC)."
    }

    fn supports_incremental(&self) -> bool {
        true
    }

    fn check(&self, board: &BoardState, constraints: &ConstraintSet) -> Vec<Violation> {
        if board.traces.is_empty() || constraints.noise_domains.is_empty() {
            return Vec::new();
        }

        // Index traces and net classes by net once; the same nets repeat
        // across domains and emitter/victim pairs.
        let mut segs_by_net: HashMap<&str, Vec<&Line<f64>>> = HashMap::new();
        for t in &board.traces {
            segs_by_net
                .entry(&t.net.0)
                .or_default()
                .extend(t.segments.iter());
        }
        let class_by_net: HashMap<&str, &crate::board::NetClassName> = board
            .nets
            .iter()
            .map(|n| (n.name.0.as_str(), &n.class))
            .collect();

        let mut violations = Vec::new();
        for domain in &constraints.noise_domains {
            let max_run = domain.max_parallel_run_mm;
            if max_run <= 0.0 {
                continue;
            }
            for emitter_net in &domain.emitters {
                for victim_net in &domain.victims {
                    if emitter_net == victim_net {
                        continue;
                    }
                    if let Some(v) = check_net_pair(
                        constraints,
                        &board.net_class_rules,
                        &segs_by_net,
                        &class_by_net,
                        emitter_net,
                        victim_net,
                        max_run,
                    ) {
                        violations.push(v);
                    }
                }
            }
        }
        violations
    }
}

fn check_net_pair(
    constraints: &ConstraintSet,
    net_class_rules: &HashMap<crate::board::NetClassName, crate::board::NetClassRules>,
    segs_by_net: &HashMap<&str, Vec<&Line<f64>>>,
    class_by_net: &HashMap<&str, &crate::board::NetClassName>,
    emitter_net: &str,
    victim_net: &str,
    max_run: f64,
) -> Option<Violation> {
    let emitter_segs = segs_by_net.get(emitter_net)?;
    let victim_segs = segs_by_net.get(victim_net)?;

    if emitter_segs.is_empty() || victim_segs.is_empty() {
        return None;
    }

    let emitter_class = class_by_net.get(emitter_net).copied();
    let victim_class = class_by_net.get(victim_net).copied();
    let separation = match (emitter_class, victim_class) {
        (Some(ec), Some(vc)) => {
            clearance_between(constraints, net_class_rules, ec, vc)
        }
        _ => DEFAULT_SEPARATION_MM,
    };
    let max_sep = separation * 2.0;

    let total_parallel_mm = parallel_run_length(emitter_segs, victim_segs, max_sep);

    if total_parallel_mm > max_run {
        Some(violation(
            Severity::Error,
            "EMC_PRL_001",
            &format!(
                "Parallel run {:.2} mm between emitter net '{}' and victim net '{}' exceeds limit of {:.2} mm in noise domain",
                total_parallel_mm, emitter_net, victim_net, max_run,
            ),
            DrcCategory::Emc,
            "routing_parallel_run",
            vec![emitter_net.to_owned(), victim_net.to_owned()],
            None,
            serde_json::json!({
                "emitter_net": emitter_net,
                "victim_net": victim_net,
                "parallel_run_mm": total_parallel_mm,
                "max_allowed_mm": max_run,
                "excess_mm": total_parallel_mm - max_run,
                "separation_mm": separation,
            }),
        ))
    } else {
        None
    }
}

fn parallel_run_length(emitter_segs: &[&Line<f64>], victim_segs: &[&Line<f64>], max_sep: f64) -> f64 {
    let mut total = 0.0;
    // Each segment's angle is invariant across the E×V loop; precompute both
    // angle vectors once instead of calling line_angle() (atan2) per pair.
    let e_angles: Vec<f64> = emitter_segs.iter().map(|s| line_angle(s)).collect();
    let v_angles: Vec<f64> = victim_segs.iter().map(|s| line_angle(s)).collect();
    for (e_idx, e_seg) in emitter_segs.iter().enumerate() {
        let e_angle = e_angles[e_idx];
        // Project both segments onto the emitter's direction: the emitter
        // projects to the interval [0, len]; each victim's endpoint projections
        // bound its interval on the same axis. The parallel run for the pair is
        // the overlap of the two intervals. (Fixes a former bug where `run` was
        // the distance from each segment to its OWN start point, i.e. always
        // 0.0, so the check never fired.)
        let (ex0, ey0) = (e_seg.start.x, e_seg.start.y);
        let e_len = ((e_seg.end.x - ex0).powi(2) + (e_seg.end.y - ey0).powi(2)).sqrt();
        if e_len < 1e-9 {
            continue;
        }
        let (udx, udy) = ((e_seg.end.x - ex0) / e_len, (e_seg.end.y - ey0) / e_len);
        for (v_idx, v_seg) in victim_segs.iter().enumerate() {
            let v_angle = v_angles[v_idx];
            if angles_parallel(e_angle, v_angle) {
                let seg_dist = e_seg.euclidean_distance(*v_seg);
                if seg_dist < max_sep {
                    let v0 = (v_seg.start.x - ex0) * udx + (v_seg.start.y - ey0) * udy;
                    let v1 = (v_seg.end.x - ex0) * udx + (v_seg.end.y - ey0) * udy;
                    let (lo, hi) = if v0 <= v1 { (v0, v1) } else { (v1, v0) };
                    let run = (e_len.min(hi) - 0.0f64.max(lo)).max(0.0);
                    total += run;
                }
            }
        }
    }
    total
}

/// Compute the angle (in radians) of a line segment from start to end.
fn line_angle(line: &Line<f64>) -> f64 {
    let dx = line.end.x - line.start.x;
    let dy = line.end.y - line.start.y;
    dy.atan2(dx)
}

/// Returns true if the absolute angular difference (mod π) between two
/// angles is within PARALLEL_ANGLE_TOLERANCE_RAD.
fn angles_parallel(a: f64, b: f64) -> bool {
    let diff = (a - b).abs() % PI;
    let wrapped = diff.min(PI - diff);
    wrapped <= PARALLEL_ANGLE_TOLERANCE_RAD
}
