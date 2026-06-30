// Routing check: isolation barrier crossing.
//
// For each IsolationBarrier in constraints, creates a geo::Line from
// (barrier.x_mm, y_span[0]) to (barrier.x_mm, y_span[1]).  Then checks
// every TraceSegment and CopperZone for intersection with the barrier line.
// If any trace segment or zone polygon intersects the barrier, a CRITICAL
// Safety violation is emitted.
//
// Degenerate case: 0 barriers → empty violations vec.
//
// Origin: U4 of docs/plans/2026-06-30-003-feat-temper-drc-rs-engine-plan.md

use crate::board::BoardState;
use crate::constraints::ConstraintSet;
use crate::rules::{violation, DrcCategory, DrcRule, Severity, Violation};

use geo::{Centroid, Intersects, Line, Point};

pub struct IsolationBarrierCheck;

impl IsolationBarrierCheck {
    pub fn new() -> Self {
        Self
    }
}

impl DrcRule for IsolationBarrierCheck {
    fn name(&self) -> &str {
        "routing_isolation_barrier"
    }

    fn category(&self) -> DrcCategory {
        DrcCategory::Safety
    }

    fn description(&self) -> &str {
        "Verify no copper crosses an isolation barrier — critical for safety isolation."
    }

    fn check(&self, board: &BoardState, constraints: &ConstraintSet) -> Vec<Violation> {
        let mut violations = Vec::new();

        // Degenerate: no isolation barriers defined.
        if constraints.isolation_barriers.is_empty() {
            return violations;
        }

        for barrier in &constraints.isolation_barriers {
            // Build the barrier line.
            let barrier_line = Line::new(
                geo::Coord {
                    x: barrier.x_mm,
                    y: barrier.y_span[0],
                },
                geo::Coord {
                    x: barrier.x_mm,
                    y: barrier.y_span[1],
                },
            );

            let barrier_name = &barrier.name;

            // Check trace segments for intersection.
            for trace in &board.traces {
                for segment in &trace.segments {
                    if segment.intersects(&barrier_line) {
                        let mid = geo::Point::new(
                            (segment.start.x + segment.end.x) / 2.0,
                            (segment.start.y + segment.end.y) / 2.0,
                        );
                        violations.push(violation(
                            Severity::Critical,
                            "ROUTING_ISO_001",
                            &format!(
                                "Trace '{}' crosses isolation barrier '{}' on {}.",
                                trace.net, barrier_name, trace.layer,
                            ),
                            DrcCategory::Safety,
                            "routing_isolation_barrier",
                            vec![trace.net.0.clone(), barrier_name.clone()],
                            Some(crate::rules::Location {
                                x: Some(mid.x()),
                                y: Some(mid.y()),
                                layer: Some(trace.layer.clone()),
                            }),
                            serde_json::json!({
                                "barrier": barrier_name,
                                "barrier_x_mm": barrier.x_mm,
                                "barrier_y_span": barrier.y_span,
                                "trace_net": trace.net,
                            }),
                        ));
                    }
                }
            }

            // Check copper zones for intersection.
            for zone in &board.zones {
                // Use Polygon's intersects method against the barrier line.
                if zone.polygon.intersects(&barrier_line) {
                    let centroid = zone.polygon.centroid().unwrap_or(Point::new(0.0, 0.0));
                    violations.push(violation(
                        Severity::Critical,
                        "ROUTING_ISO_002",
                        &format!(
                            "Copper zone '{}' on {} crosses isolation barrier '{}'.",
                            zone.net, zone.layer, barrier_name,
                        ),
                        DrcCategory::Safety,
                        "routing_isolation_barrier",
                        vec![zone.net.0.clone(), barrier_name.clone()],
                        Some(crate::rules::Location {
                            x: Some(centroid.x()),
                            y: Some(centroid.y()),
                            layer: Some(zone.layer.clone()),
                        }),
                        serde_json::json!({
                            "barrier": barrier_name,
                            "barrier_x_mm": barrier.x_mm,
                            "barrier_y_span": barrier.y_span,
                            "zone_net": zone.net,
                        }),
                    ));
                }
            }
        }

        violations
    }
}
