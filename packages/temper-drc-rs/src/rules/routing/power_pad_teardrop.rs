// Routing check: power-pad teardrop — trace width at pad junction.
//
// For each trace where the net's max_current_rating >= 5.0 A, inspect
// both endpoints of every segment.  If an endpoint lands within 0.5 mm
// of a component footprint edge, verify the trace width is >= 60 % of
// the pad dimension measured in the direction the trace enters.
//
// Narrower traces emit WARNING DFM violations.
//
// Degenerate: 0 high-current traces → empty vec.
//
// Origin: U4 of docs/plans/2026-06-30-003-feat-temper-drc-rs-engine-plan.md

use geo::{EuclideanDistance, Point};

use crate::board::{BoardSide, BoardState, NetClassName};
use crate::constraints::ConstraintSet;
use crate::rules::{violation, DrcCategory, DrcRule, Location, Severity, Violation};

/// A trace endpoint must be within this distance (mm) of a component's
/// footprint edge to be considered a pad junction.
const PAD_TOUCH_DISTANCE_MM: f64 = 0.5;

/// Minimum ratio of trace width to the pad dimension at the junction.
const MIN_WIDTH_RATIO: f64 = 0.6;

/// Minimum current threshold (A) — traces below this are skipped.
const MIN_CURRENT_A: f64 = 5.0;

// ---------------------------------------------------------------------------
// Helper
// ---------------------------------------------------------------------------

/// Determine which pad dimension is relevant based on entry direction.
///
/// When a trace enters from the left or right side of a component, the
/// trace is travelling horizontally and the relevant pad dimension is
/// the component's height (vertical extent).  When entering from top or
/// bottom, the relevant dimension is the component's width.
fn pad_dimension_in_entry_direction(comp: &crate::board::Component, ep: &Point<f64>) -> f64 {
    let dx = ep.x() - comp.center.x();
    let dy = ep.y() - comp.center.y();
    // Normalise by dimension so that non-square footprints are handled
    // proportionally.  If the endpoint is proportionally closer to a
    // horizontal edge than a vertical edge → entering from left/right.
    if comp.width > 0.0 && comp.height > 0.0 && dx.abs() / comp.width > dy.abs() / comp.height {
        comp.height
    } else {
        comp.width
    }
}

// ---------------------------------------------------------------------------
// Check
// ---------------------------------------------------------------------------

pub struct PowerPadTeardropCheck;

impl PowerPadTeardropCheck {
    pub fn new() -> Self {
        Self
    }
}

impl DrcRule for PowerPadTeardropCheck {
    fn name(&self) -> &str {
        "routing_power_pad_teardrop"
    }

    fn category(&self) -> DrcCategory {
        DrcCategory::Dfm
    }

    fn description(&self) -> &str {
        "Check that power traces (>= 5.0 A) have adequate width at pad junctions (>= 60 % of pad dimension)."
    }

    fn check(&self, board: &BoardState, _constraints: &ConstraintSet) -> Vec<Violation> {
        let mut violations = Vec::new();

        // ---- 1. Identify high-current net classes (max_current_rating >= 5.0 A) ---
        let class_names: Vec<NetClassName> = board
            .net_class_rules
            .iter()
            .filter(|(_, rules)| rules.max_current_rating.map_or(false, |r| r >= MIN_CURRENT_A))
            .map(|(name, _)| name.clone())
            .collect();

        if class_names.is_empty() {
            return violations;
        }

        // Nets belonging to those high-current classes.
        let high_cur_nets: Vec<&str> = board
            .nets
            .iter()
            .filter(|n| class_names.contains(&n.class))
            .map(|n| n.name.0.as_str())
            .collect();

        if high_cur_nets.is_empty() {
            return violations;
        }

        // ---- 2. Build a spatial lookup: for each component, its layer string ----
        fn comp_layer(side: BoardSide) -> &'static str {
            match side {
                BoardSide::Top => "F.Cu",
                BoardSide::Bottom => "B.Cu",
            }
        }

        // ---- 3. Iterate traces ---------------------------------------------------
        for trace in &board.traces {
            if !high_cur_nets.contains(&trace.net.0.as_str()) {
                continue;
            }

            for seg in &trace.segments {
                for ep in [seg.start, seg.end] {
                    let ep_point = Point::new(ep.x, ep.y);

                    // Find which component (if any) this endpoint touches
                    for comp in &board.electrical_components {
                        // Layer check: trace layer must match component side
                        if trace.layer != comp_layer(comp.side) {
                            continue;
                        }

                        // Distance from endpoint to component footprint edge
                        let dist_to_edge = match &comp.footprint_polygon {
                            Some(poly) => poly.euclidean_distance(&ep_point),
                            None => {
                                // Fallback: distance to nearest bbox edge
                                let bbox = comp.footprint_bbox();
                                distance_to_rect_edge(&bbox, &ep_point)
                            }
                        };

                        if dist_to_edge > PAD_TOUCH_DISTANCE_MM {
                            continue;
                        }

                        // Compute the pad dimension in the direction the trace enters
                        let pad_dim = pad_dimension_in_entry_direction(comp, &ep_point);
                        let required_width = pad_dim * MIN_WIDTH_RATIO;

                        if trace.width < required_width {
                            let violation_msg = format!(
                                "Trace {} on {} width {:.3} mm < {:.3} mm (60 % of pad dim {:.3} mm) at pad junction near {}",
                                trace.net, trace.layer, trace.width, required_width, pad_dim, comp.refdes,
                            );

                            violations.push(violation(
                                Severity::Warning,
                                "DFM_TDR_001",
                                &violation_msg,
                                DrcCategory::Dfm,
                                "routing_power_pad_teardrop",
                                vec![trace.net.0.clone(), comp.refdes.0.clone()],
                                Some(Location {
                                    x: Some(ep.x),
                                    y: Some(ep.y),
                                    layer: Some(trace.layer.clone()),
                                }),
                                serde_json::json!({
                                    "trace_width_mm": trace.width,
                                    "required_width_mm": required_width,
                                    "pad_dimension_mm": pad_dim,
                                    "min_ratio": MIN_WIDTH_RATIO,
                                    "component": comp.refdes,
                                }),
                            ));
                        }

                        // Only report once per endpoint (first touching component wins)
                        break;
                    }
                }
            }
        }

        violations
    }
}

/// Distance from a point to the nearest edge of an axis-aligned rectangle.
/// Returns 0.0 if the point is inside the rectangle.
fn distance_to_rect_edge(rect: &geo::Rect<f64>, point: &Point<f64>) -> f64 {
    let dx = if point.x() < rect.min().x {
        rect.min().x - point.x()
    } else if point.x() > rect.max().x {
        point.x() - rect.max().x
    } else {
        0.0
    };
    let dy = if point.y() < rect.min().y {
        rect.min().y - point.y()
    } else if point.y() > rect.max().y {
        point.y() - rect.max().y
    } else {
        0.0
    };
    (dx * dx + dy * dy).sqrt()
}

#[cfg(test)]
mod tests {
    use super::*;
    use geo::point;

    #[test]
    fn test_distance_to_rect_edge_inside() {
        let rect = geo::Rect::new(geo::coord! { x: 0.0, y: 0.0 }, geo::coord! { x: 10.0, y: 10.0 });
        let p = point! { x: 5.0, y: 5.0 };
        assert_eq!(distance_to_rect_edge(&rect, &p), 0.0);
    }

    #[test]
    fn test_distance_to_rect_edge_outside() {
        let rect = geo::Rect::new(geo::coord! { x: 0.0, y: 0.0 }, geo::coord! { x: 10.0, y: 10.0 });
        let p = point! { x: 15.0, y: 5.0 };
        assert!((distance_to_rect_edge(&rect, &p) - 5.0).abs() < 1e-9);
    }
}
