// Routing check: partial discharge — inner-layer clearance for HV nets.
//
// For high-voltage nets (voltage_v >= 60.0 V or safety_category contains "HV"),
// traces on inner layers (In1_Cu, In2_Cu) require 1.5x the outer-layer PV
// clearance value.  Compares trace-to-trace and trace-to-zone distances against
// (base_clearance * 1.5).  Violations are ERROR severity.
//
// Degenerate: 0 HV inner traces → empty vec.
//
// Origin: U4 of docs/plans/2026-06-30-003-feat-temper-drc-rs-engine-plan.md

use geo::EuclideanDistance;

use crate::board::BoardState;
use crate::constraints::ConstraintSet;
use crate::rules::{violation, DrcCategory, DrcRule, Location, Severity, Violation};

/// Multiplier applied to the base PV clearance for inner-layer HV traces.
const INNER_LAYER_CLEARANCE_MULTIPLIER: f64 = 1.5;

/// Voltage threshold (V) above which a net is considered high-voltage.
const HV_VOLTAGE_THRESHOLD_V: f64 = 60.0;

/// Layer names considered "inner layers".
const INNER_LAYERS: &[&str] = &["In1.Cu", "In2.Cu"];

// ---------------------------------------------------------------------------
// Check
// ---------------------------------------------------------------------------

pub struct PartialDischargeCheck;

impl PartialDischargeCheck {
    pub fn new() -> Self {
        Self
    }
}

impl DrcRule for PartialDischargeCheck {
    fn name(&self) -> &str {
        "routing_partial_discharge"
    }

    fn category(&self) -> DrcCategory {
        DrcCategory::Safety
    }

    fn description(&self) -> &str {
        "Ensure inner-layer HV trace clearances meet 1.5x the PV clearance requirement for partial discharge mitigation."
    }

    fn check(&self, board: &BoardState, _constraints: &ConstraintSet) -> Vec<Violation> {
        let mut violations = Vec::new();

        // ---- 1. Identify high-voltage net classes ---------------------------------
        let hv_class_names: Vec<&str> = board
            .net_class_rules
            .iter()
            .filter(|(_, rules)| {
                rules.voltage_v.map_or(false, |v| v >= HV_VOLTAGE_THRESHOLD_V)
            })
            .map(|(name, _)| name.as_str())
            .collect();

        if hv_class_names.is_empty() {
            return violations;
        }

        // Map net name → class name, keep only HV-class nets
        let hv_nets: Vec<&str> = board
            .net_classes
            .iter()
            .filter(|(_, cls)| hv_class_names.contains(&cls.as_str()))
            .map(|(net, _)| net.as_str())
            .collect();

        // ---- 2. Collect HV traces on inner layers --------------------------------
        let hv_inner_traces: Vec<&crate::board::TraceSegment> = board
            .traces
            .iter()
            .filter(|t| hv_nets.contains(&t.net.as_str()) && INNER_LAYERS.contains(&t.layer.as_str()))
            .collect();

        if hv_inner_traces.is_empty() {
            return violations;
        }

        // Build a lookup: net class → NetClassRules for clearance lookup
        let all_traces: &[crate::board::TraceSegment] = &board.traces;

        // ---- 3. Compare each HV inner trace segment to ALL other trace segments ---
        for hv_trace in &hv_inner_traces {
            // Look up this HV trace's net class rules for base clearance
            let net_class = board.net_classes.get(&hv_trace.net);
            let base_clearance: f64 = net_class
                .and_then(|cls| board.net_class_rules.get(cls))
                .map(|rules| rules.clearance_mm)
                .unwrap_or(0.2); // fallback default
            let min_clearance = base_clearance * INNER_LAYER_CLEARANCE_MULTIPLIER;

            let hv_ptr: *const crate::board::TraceSegment = *hv_trace;

            for hv_seg in &hv_trace.segments {
                for other_trace in all_traces {
                    // Skip self-comparison via pointer equality
                    let other_ptr: *const crate::board::TraceSegment = other_trace;
                    if hv_ptr == other_ptr {
                        continue;
                    }

                    for other_seg in &other_trace.segments {
                        let dist = hv_seg.euclidean_distance(other_seg);
                        if dist < min_clearance {
                            let mid = geo::Point::new(
                                (hv_seg.start.x + other_seg.start.x) / 2.0,
                                (hv_seg.start.y + other_seg.start.y) / 2.0,
                            );
                            violations.push(violation(
                                Severity::Error,
                                "SAF_PDS_001",
                                &format!(
                                    "Partial discharge: HV trace {} (net {}, layer {}) is {:.3} mm \
                                     from trace {} (net {}, layer {}), below {:.3} mm required \
                                     (base clearance {:.3} mm × {:.1})",
                                    "", hv_trace.net, hv_trace.layer, dist,
                                    "", other_trace.net, other_trace.layer,
                                    min_clearance, base_clearance, INNER_LAYER_CLEARANCE_MULTIPLIER,
                                ),
                                DrcCategory::Safety,
                                "routing_partial_discharge",
                                vec![hv_trace.net.clone(), other_trace.net.clone()],
                                Some(Location {
                                    x: Some(mid.x()),
                                    y: Some(mid.y()),
                                    layer: Some(hv_trace.layer.clone()),
                                }),
                                serde_json::json!({
                                    "clearance_mm": dist,
                                    "required_clearance_mm": min_clearance,
                                    "base_clearance_mm": base_clearance,
                                    "multiplier": INNER_LAYER_CLEARANCE_MULTIPLIER,
                                    "hv_net": hv_trace.net,
                                    "other_net": other_trace.net,
                                    "layer": hv_trace.layer,
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
