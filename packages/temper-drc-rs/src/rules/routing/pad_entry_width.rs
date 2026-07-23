// Routing check: pad entry width — high-current trace width at pad.
//
// For each trace where the net's max_current_rating >= 20.0 A, inspect
// endpoints at component pads.  Verify trace width >= 0.6 * pad_width
// (minimum entry ratio).  Narrower traces emit ERROR DFM violations.
//
// Degenerate: 0 high-current traces → empty vec.
//
// Origin: U4 of docs/plans/2026-06-30-003-feat-temper-drc-rs-engine-plan.md

use geo::{EuclideanDistance, Point};

use crate::board::{BoardSide, BoardState, NetClassName, TraceSegment};
use crate::constraints::ConstraintSet;
use crate::rules::{violation, DrcCategory, DrcRule, Location, Severity, Violation};

/// A trace endpoint must be within this distance (mm) of a component's
/// footprint edge to be considered a pad junction.
const PAD_TOUCH_DISTANCE_MM: f64 = 0.5;

/// Minimum ratio of trace width to the pad width at the junction.
const MIN_ENTRY_RATIO: f64 = 0.6;

/// Current threshold (A) — only traces at or above this are checked.
const HIGH_CUR_THRESHOLD_A: f64 = 20.0;

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
    if comp.width > 0.0 && comp.height > 0.0 && dx.abs() / comp.width > dy.abs() / comp.height {
        comp.height
    } else {
        comp.width
    }
}

/// Map a board side to its copper layer name.
fn comp_layer(side: BoardSide) -> &'static str {
    match side {
        BoardSide::Top => "F.Cu",
        BoardSide::Bottom => "B.Cu",
    }
}

/// Collect the net names belonging to net classes whose
/// `max_current_rating` is at or above `min_current` (A).
fn collect_high_current_net_names(board: &BoardState, min_current: f64) -> Vec<&str> {
    let class_names: Vec<NetClassName> = board
        .net_class_rules
        .iter()
        .filter(|(_, rules)| rules.max_current_rating.is_some_and(|r| r >= min_current))
        .map(|(name, _)| name).cloned()
        .collect();
    if class_names.is_empty() {
        return Vec::new();
    }
    board
        .nets
        .iter()
        .filter(|n| class_names.contains(&n.class))
        .map(|n| n.name.0.as_str())
        .collect()
}

/// Check whether a trace endpoint at a component pad meets the minimum
/// pad entry width requirement (>= 60 % of the pad dimension in the
/// entry direction). Returns `None` if no violation is found.
fn check_endpoint_pad_entry_width(
    ep_x: f64,
    ep_y: f64,
    trace: &TraceSegment,
    board: &BoardState,
) -> Option<Violation> {
    let ep_point = Point::new(ep_x, ep_y);
    for comp in &board.electrical_components {
        if trace.layer != comp_layer(comp.side) {
            continue;
        }
        let dist_to_edge = match &comp.footprint_polygon {
            Some(poly) => poly.euclidean_distance(&ep_point),
            None => distance_to_rect_edge(&comp.footprint_bbox(), &ep_point),
        };
        if dist_to_edge > PAD_TOUCH_DISTANCE_MM {
            continue;
        }
        let pad_dim = pad_dimension_in_entry_direction(comp, &ep_point);
        let required_width = pad_dim * MIN_ENTRY_RATIO;
        if trace.width < required_width {
            return Some(violation(
                Severity::Error,
                "DFM_PEW_001",
                &format!(
                    "High-current trace {} on {} width {:.3} mm < {:.3} mm \
                     (60 % of pad dim {:.3} mm) at {} pad entry",
                    trace.net, trace.layer, trace.width, required_width,
                    pad_dim, comp.refdes,
                ),
                DrcCategory::Dfm,
                "routing_pad_entry_width",
                vec![trace.net.0.clone(), comp.refdes.0.clone()],
                Some(Location {
                    x: Some(ep_x),
                    y: Some(ep_y),
                    layer: Some(trace.layer.clone()),
                }),
                serde_json::json!({
                    "trace_width_mm": trace.width,
                    "required_width_mm": required_width,
                    "pad_dimension_mm": pad_dim,
                    "min_entry_ratio": MIN_ENTRY_RATIO,
                    "component": comp.refdes,
                    "max_current_rating_a": HIGH_CUR_THRESHOLD_A,
                }),
            ));
        }
        // First matching component wins for this endpoint.
        break;
    }
    None
}

// ---------------------------------------------------------------------------
// Check
// ---------------------------------------------------------------------------

#[derive(Default)]
pub struct PadEntryWidthCheck;

impl PadEntryWidthCheck {
    pub fn new() -> Self {
        Self
    }
}

impl DrcRule for PadEntryWidthCheck {
    fn name(&self) -> &str {
        "routing_pad_entry_width"
    }

    fn category(&self) -> DrcCategory {
        DrcCategory::Dfm
    }

    fn description(&self) -> &str {
        "Verify high-current trace (>= 20.0 A) width >= 60 % of pad width at entry."
    }

    fn check(&self, board: &BoardState, _constraints: &ConstraintSet) -> Vec<Violation> {
        let mut violations = Vec::new();

        let high_cur_nets = collect_high_current_net_names(board, HIGH_CUR_THRESHOLD_A);
        if high_cur_nets.is_empty() {
            return violations;
        }

        for trace in &board.traces {
            if !high_cur_nets.contains(&trace.net.0.as_str()) {
                continue;
            }
            for seg in &trace.segments {
                for ep in [seg.start, seg.end] {
                    if let Some(v) = check_endpoint_pad_entry_width(ep.x, ep.y, trace, board) {
                        violations.push(v);
                    }
                }
            }
        }

        violations
    }
}

/// Distance from a point to the nearest edge of an axis-aligned rectangle.
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
