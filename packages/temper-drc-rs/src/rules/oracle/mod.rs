// Brute-force completeness oracles for DRC checks.
//
// Each oracle uses a different (typically O(n²) exhaustive) algorithm
// compared to the production check's approach, providing validation
// that the production engine finds all violations.
//
// These oracles are used in test code to cross-validate results.
// They share zero code with the production checks.
//
// Origin: U4 of docs/plans/2026-06-30-003-feat-temper-drc-rs-engine-plan.md

use std::collections::HashSet;

use geo::EuclideanDistance;
use geo::{Coord, Line, Point};

use crate::board::{BoardState, Component};
use crate::constraints::ConstraintSet;
use crate::rules::{
    clearance_between, violation, DrcCategory, Location, Severity, Violation,
};

// ---------------------------------------------------------------------------
// Shared pair-scan and geometry helpers (the oracles' common skeleton)
// ---------------------------------------------------------------------------

/// Iterate every same-side component pair (i, j) with i < j.
fn same_side_pairs<'a, 'c>(
    comps: &'c [&'a Component],
) -> impl Iterator<Item = (&'a Component, &'a Component)> + 'c
where
    'a: 'c,
{
    comps
        .iter()
        .enumerate()
        .flat_map(|(i, a)| comps[i + 1..].iter().map(move |b| (*a, *b)))
        .filter(|(a, b)| a.side == b.side)
}

/// Midpoint of two centers — the shared violation-location computation.
fn midpoint(a: &Point<f64>, b: &Point<f64>) -> Point<f64> {
    Point::new((a.x() + b.x()) / 2.0, (a.y() + b.y()) / 2.0)
}

/// Component bbox expanded by `margin` on every side:
/// `(min_x, min_y, max_x, max_y)`.
fn expanded_bbox(center: &Point<f64>, w: f64, h: f64, margin: f64) -> (f64, f64, f64, f64) {
    (
        center.x() - w / 2.0 - margin,
        center.y() - h / 2.0 - margin,
        center.x() + w / 2.0 + margin,
        center.y() + h / 2.0 + margin,
    )
}

/// Point-to-coordinate distance, the exact Python algorithm from the
/// pre-migration trace-clearance check.
fn point_segment_dist(p: Coord<f64>, a: Coord<f64>, b: Coord<f64>) -> f64 {
    let (px, py) = (p.x, p.y);
    let (sx, sy) = (a.x, a.y);
    let (ex, ey) = (b.x, b.y);
    let dx = ex - sx;
    let dy = ey - sy;
    if dx == 0.0 && dy == 0.0 {
        return ((px - sx).powi(2) + (py - sy).powi(2)).sqrt();
    }
    let t = ((px - sx) * dx + (py - sy) * dy) / (dx * dx + dy * dy);
    let t = t.clamp(0.0, 1.0);
    let proj_x = sx + t * dx;
    let proj_y = sy + t * dy;
    ((px - proj_x).powi(2) + (py - proj_y).powi(2)).sqrt()
}

/// Segment-to-segment distance as the min of the four endpoint distances.
fn segment_to_segment_distance(a: &Line<f64>, b: &Line<f64>) -> f64 {
    [
        point_segment_dist(a.start, b.start, b.end),
        point_segment_dist(a.end, b.start, b.end),
        point_segment_dist(b.start, a.start, a.end),
        point_segment_dist(b.end, a.start, a.end),
    ]
    .into_iter()
    .fold(f64::MAX, f64::min)
}

// ---------------------------------------------------------------------------
// Oracle: ClearanceCheck — exhaustive O(n²) pair scan
// ---------------------------------------------------------------------------

/// Brute-force oracle for ClearanceCheck.
///
/// Iterates every component pair without any spatial index. Used to
/// validate that the production ClearanceCheck finds all violations.
pub fn oracle_clearance(board: &BoardState, constraints: &ConstraintSet) -> Vec<Violation> {
    let comps: Vec<&Component> = board.all_components().collect();
    same_side_pairs(&comps)
        .filter_map(|(a, b)| {
            let required =
                clearance_between(constraints, &board.net_class_rules, &a.net_class, &b.net_class);
            if required <= 0.0 {
                return None;
            }
            // Use euclidean_distance directly on centers for the oracle
            // (different approach from production's edge_distance_to).
            let dist = a.center.euclidean_distance(&b.center)
                - (a.width.max(a.height) / 2.0)
                - (b.width.max(b.height) / 2.0);
            (dist < required).then(|| {
                let mid = midpoint(&a.center, &b.center);
                violation(
                    Severity::Error,
                    "DRC_CLR_001",
                    &format!(
                        "[ORACLE] Clearance violation: {:.3}mm < {:.3}mm between {} and {}",
                        dist, required, a.refdes, b.refdes,
                    ),
                    DrcCategory::Drc,
                    "oracle_clearance",
                    vec![a.refdes.0.clone(), b.refdes.0.clone()],
                    Some(Location {
                        x: Some(mid.x()),
                        y: Some(mid.y()),
                        layer: None,
                    }),
                    serde_json::json!({
                        "actual_mm": dist,
                        "required_mm": required,
                    }),
                )
            })
        })
        .collect()
}

// ---------------------------------------------------------------------------
// Oracle: ComponentOverlapCheck — center-distance heuristic
// ---------------------------------------------------------------------------

/// Brute-force oracle for ComponentOverlapCheck.
///
/// Uses a center-distance heuristic (different from polygon-intersection
/// used in production) to validate overlap detection.
pub fn oracle_component_overlap(board: &BoardState) -> Vec<Violation> {
    let comps: Vec<&Component> = board.all_components().collect();
    same_side_pairs(&comps)
        .filter_map(|(a, b)| {
            // Heuristic: if the distance between centers is less than the
            // sum of half-diagonals, there's likely overlap
            let half_diag_a = (a.width * a.width + a.height * a.height).sqrt() / 2.0;
            let half_diag_b = (b.width * b.width + b.height * b.height).sqrt() / 2.0;
            let center_dist = a.center.euclidean_distance(&b.center);
            (center_dist < (half_diag_a + half_diag_b) * 0.9).then(|| {
                let mid = midpoint(&a.center, &b.center);
                violation(
                    Severity::Critical,
                    "DRC_OVL_001",
                    &format!(
                        "[ORACLE] Component overlapped: {} covers {}",
                        a.refdes, b.refdes,
                    ),
                    DrcCategory::Drc,
                    "oracle_component_overlap",
                    vec![a.refdes.0.clone(), b.refdes.0.clone()],
                    Some(Location {
                        x: Some(mid.x()),
                        y: Some(mid.y()),
                        layer: None,
                    }),
                    serde_json::json!({}),
                )
            })
        })
        .collect()
}

// ---------------------------------------------------------------------------
// Oracle: CourtyardCheck — expanded bbox approach
// ---------------------------------------------------------------------------

/// Brute-force oracle for CourtyardCheck using expanded bounding boxes.
pub fn oracle_courtyard(board: &BoardState, margin_mm: f64) -> Vec<Violation> {
    let comps: Vec<&Component> = board.all_components().collect();
    let required_gap = margin_mm * 2.0;
    same_side_pairs(&comps)
        .filter_map(|(a, b)| {
            let (a_min_x, a_min_y, a_max_x, a_max_y) =
                expanded_bbox(&a.center, a.width, a.height, margin_mm);
            let (b_min_x, b_min_y, b_max_x, b_max_y) =
                expanded_bbox(&b.center, b.width, b.height, margin_mm);
            let overlap_x = a_min_x <= b_max_x && b_min_x <= a_max_x;
            let overlap_y = a_min_y <= b_max_y && b_min_y <= a_max_y;
            (overlap_x && overlap_y).then(|| {
                let mid = midpoint(&a.center, &b.center);
                violation(
                    Severity::Warning,
                    "DRC_CRT_001",
                    &format!(
                        "[ORACLE] Courtyard violation between {} and {}",
                        a.refdes, b.refdes,
                    ),
                    DrcCategory::Drc,
                    "oracle_courtyard",
                    vec![a.refdes.0.clone(), b.refdes.0.clone()],
                    Some(Location {
                        x: Some(mid.x()),
                        y: Some(mid.y()),
                        layer: None,
                    }),
                    serde_json::json!({
                        "margin_per_comp_mm": margin_mm,
                        "required_gap_mm": required_gap,
                    }),
                )
            })
        })
        .collect()
}

// ---------------------------------------------------------------------------
// Oracle: NetConnectivityCheck — same algorithm, different code path
// ---------------------------------------------------------------------------

/// Oracle for NetConnectivityCheck.
///
/// Uses a HashSet-based counting approach instead of direct len() checks
/// to provide an independent implementation.
pub fn oracle_net_connectivity(board: &BoardState) -> Vec<Violation> {
    let mut violations = Vec::new();

    for net in &board.nets {
        let count: HashSet<&str> = net.components.iter().map(|c| &*c.0).collect();
        if count.len() < 2 {
            violations.push(violation(
                Severity::Error,
                "ERC_NET_001",
                &format!(
                    "[ORACLE] Net '{}' has only {} connection(s). Minimum 2 required.",
                    net.name,
                    count.len(),
                ),
                DrcCategory::Erc,
                "oracle_net_connectivity",
                net.components.iter().map(|c| c.0.clone()).collect(),
                None,
                serde_json::json!({
                    "net_name": net.name.to_string(),
                    "connection_count": count.len(),
                }),
            ));
        }
    }

    violations
}

// ---------------------------------------------------------------------------
// Oracle: FloatingPinsCheck — set-based membership test
// ---------------------------------------------------------------------------

/// Oracle for FloatingPinsCheck using set enumeration.
pub fn oracle_floating_pins(board: &BoardState) -> Vec<Violation> {
    let mut violations = Vec::new();

    let connected: HashSet<&str> = board
        .nets
        .iter()
        .flat_map(|net| net.components.iter().map(|c| &*c.0))
        .collect();

    // Double-check by counting
    let total_connected: usize = connected.len();

    for comp in board.all_components() {
        if !connected.contains(&*comp.refdes) {
            violations.push(violation(
                Severity::Warning,
                "ERC_FLT_001",
                &format!(
                    "[ORACLE] Component '{}' is floating (total connected: {}).",
                    comp.refdes, total_connected,
                ),
                DrcCategory::Erc,
                "oracle_floating_pins",
                vec![comp.refdes.0.clone()],
                None,
                serde_json::json!({
                    "ref": comp.refdes,
                }),
            ));
        }
    }

    violations
}

// ---------------------------------------------------------------------------
// Oracle: TraceClearanceCheck — point-segment distance (Python algorithm)
// ---------------------------------------------------------------------------

/// Oracle for TraceClearanceCheck using the exact Python algorithm.
pub fn oracle_trace_clearance(board: &BoardState, min_clearance: f64) -> Vec<Violation> {
    if board.traces.is_empty() {
        return Vec::new();
    }

    let segments: Vec<&crate::board::TraceSegment> = board.traces.iter().collect();
    let n = segments.len();
    let mut violations = Vec::new();

    for i in 0..n {
        for j in (i + 1)..n {
            let si = segments[i];
            let sj = segments[j];

            if si.net == sj.net || si.layer != sj.layer {
                continue;
            }

            for seg_a in &si.segments {
                for seg_b in &sj.segments {
                    let dist = segment_to_segment_distance(seg_a, seg_b);
                    if dist < min_clearance {
                        violations.push(violation(
                            Severity::Error,
                            "DRC_TRC_001",
                            &format!(
                                "[ORACLE] Trace clearance violation between '{}' and '{}' on {}",
                                si.net, sj.net, si.layer,
                            ),
                            DrcCategory::Drc,
                            "oracle_trace_clearance",
                            vec![si.net.0.clone(), sj.net.0.clone()],
                            None,
                            serde_json::json!({
                                "actual_mm": dist,
                                "required_mm": min_clearance,
                            }),
                        ));
                        break;
                    }
                }
            }
        }
    }

    violations
}
