// DRC check: trace-to-trace clearance.
//
// For each trace segment pair on the same layer, computes the minimum
// Euclidean distance and checks against the required clearance from
// clearance_between() (net class rules). Emits DRC_TRC_001 CRITICAL.
// Degenerate: 0 traces → empty vec.
//
// Ported from: packages/temper-drc/src/temper_drc/checks/drc/trace_clearance.py
//
// Origin: U4 of docs/plans/2026-06-30-003-feat-temper-drc-rs-engine-plan.md

use crate::board::BoardState;
use crate::constraints::ConstraintSet;
use crate::rules::{clearance_between, violation, DrcCategory, DrcRule, Severity, Violation};
use geo::EuclideanDistance;
use std::collections::HashMap;

#[derive(Default)]
pub struct TraceClearanceCheck;

impl TraceClearanceCheck {
    pub fn new() -> Self {
        Self
    }
}
impl DrcRule for TraceClearanceCheck {
    fn name(&self) -> &str {
        "drc_trace_clearance"
    }
    fn category(&self) -> DrcCategory {
        DrcCategory::Drc
    }
    fn description(&self) -> &str {
        "Check trace-to-trace clearance against net class rules."
    }
    fn check(&self, board: &BoardState, constraints: &ConstraintSet) -> Vec<Violation> {
        let mut violations = Vec::new();
        let traces = &board.traces;
        let default_class = crate::board::NetClassName("Default".into());

        // Index net name → class once. board.net_by_name() is a linear scan;
        // this map turns the per-trace-pair lookup into a hash lookup.
        let net_class: HashMap<&str, &crate::board::NetClassName> = board
            .nets
            .iter()
            .map(|n| (n.name.0.as_str(), &n.class))
            .collect();

        for i in 0..traces.len() {
            for j in (i + 1)..traces.len() {
                let ta = &traces[i];
                let tb = &traces[j];
                if ta.layer != tb.layer {
                    continue;
                }

                // Net-class resolution and required clearance are invariant
                // across a trace pair's segment pairs; resolve once, not per
                // segment pair.
                let class_a = net_class
                    .get(ta.net.0.as_str())
                    .copied()
                    .unwrap_or(&default_class);
                let class_b = net_class
                    .get(tb.net.0.as_str())
                    .copied()
                    .unwrap_or(&default_class);
                let required = clearance_between(constraints, &board.net_class_rules, class_a, class_b);

                for seg_a in &ta.segments {
                    for seg_b in &tb.segments {
                        let dist = seg_a.euclidean_distance(seg_b);

                        if dist < required {
                            violations.push(violation(
                                Severity::Critical,
                                "DRC_TRC_001",
                                &format!(
                                    "Trace clearance violation: {} to {} on {} = {:.3}mm, required {:.3}mm",
                                    ta.net, tb.net, ta.layer, dist, required,
                                ),
                                DrcCategory::Drc,
                                "drc_trace_clearance",
                                vec![ta.net.0.clone(), tb.net.0.clone()],
                                None,
                                serde_json::json!({
                                    "distance_mm": dist,
                                    "required_mm": required,
                                    "layer": ta.layer,
                                }),
                            ));
                        }
                    }
                }
            }
        }
        violations
    }
}
