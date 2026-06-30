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
use std::f64::consts::PI;

use crate::board::BoardState;
use crate::constraints::ConstraintSet;
use crate::rules::{clearance_between, violation, DrcCategory, DrcRule, Severity, Violation};

/// Angle tolerance for considering two segments "parallel" (radians).
const PARALLEL_ANGLE_TOLERANCE_RAD: f64 = 10.0 * PI / 180.0; // 10°

/// Default separation clearance (mm) when net class is unknown.
const DEFAULT_SEPARATION_MM: f64 = 0.2;

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
        let mut violations = Vec::new();

        // Degenerate: no traces or no noise domains → empty
        if board.traces.is_empty() || constraints.noise_domains.is_empty() {
            return violations;
        }

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

                    // Collect all trace segments belonging to the emitter and victim nets.
                    let emitter_segs: Vec<&Line<f64>> = board
                        .traces
                        .iter()
                        .filter(|t| t.net.0 == *emitter_net)
                        .flat_map(|t| &t.segments)
                        .collect();

                    let victim_segs: Vec<&Line<f64>> = board
                        .traces
                        .iter()
                        .filter(|t| t.net.0 == *victim_net)
                        .flat_map(|t| &t.segments)
                        .collect();

                    if emitter_segs.is_empty() || victim_segs.is_empty() {
                        continue;
                    }

                    // Determine separation distance from net class clearance rules.
                    let emitter_class = board.net_by_name(emitter_net).map(|n| &n.class);
                    let victim_class = board.net_by_name(victim_net).map(|n| &n.class);
                    let separation = match (emitter_class, victim_class) {
                        (Some(ec), Some(vc)) => clearance_between(
                            constraints,
                            &board.net_class_rules,
                            ec,
                            vc,
                        ),
                        _ => DEFAULT_SEPARATION_MM,
                    };
                    let max_sep = separation * 2.0;

                    // Accumulate total parallel run length between these two nets.
                    let mut total_parallel_mm = 0.0;

                    for e_seg in &emitter_segs {
                        let e_angle = line_angle(e_seg);
                        for v_seg in &victim_segs {
                            let v_angle = line_angle(v_seg);
                            if angles_parallel(e_angle, v_angle) {
                                // Only count if segments are within separation distance.
                                let seg_dist = e_seg.euclidean_distance(*v_seg);
                                if seg_dist < max_sep {
                                    // The overlapping run contribution is the minimum of
                                    // the two segment lengths when they are parallel.
                                    let run = e_seg
                                        .euclidean_distance(&e_seg.start)
                                        .min(v_seg.euclidean_distance(&v_seg.start));
                                    total_parallel_mm += run;
                                }
                            }
                        }
                    }

                    if total_parallel_mm > max_run {
                        violations.push(violation(
                            Severity::Error,
                            "EMC_PRL_001",
                            &format!(
                                "Parallel run {:.2} mm between emitter net '{}' and victim net '{}' exceeds limit of {:.2} mm in noise domain '{}'",
                                total_parallel_mm, emitter_net, victim_net, max_run,
                                domain.emitters.first().map(|s| s.as_str()).unwrap_or("unknown"),
                            ),
                            DrcCategory::Emc,
                            "routing_parallel_run",
                            vec![emitter_net.clone(), victim_net.clone()],
                            None,
                            serde_json::json!({
                                "emitter_net": emitter_net,
                                "victim_net": victim_net,
                                "parallel_run_mm": total_parallel_mm,
                                "max_allowed_mm": max_run,
                                "excess_mm": total_parallel_mm - max_run,
                                "separation_mm": separation,
                            }),
                        ));
                    }
                }
            }
        }

        violations
    }
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
