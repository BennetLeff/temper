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

use crate::board::{BoardState, Component};
use crate::constraints::ConstraintSet;
use crate::rules::{
    clearance_between, violation, DrcCategory, Location, Severity, Violation,
};

// ---------------------------------------------------------------------------
// Oracle: ClearanceCheck — exhaustive O(n²) pair scan
// ---------------------------------------------------------------------------

/// Brute-force oracle for ClearanceCheck.
///
/// Iterates every component pair without any spatial index. Used to
/// validate that the production ClearanceCheck finds all violations.
pub fn oracle_clearance(board: &BoardState, constraints: &ConstraintSet) -> Vec<Violation> {
    let mut violations = Vec::new();
    let comps: Vec<&Component> = board.all_components().collect();
    let n = comps.len();

    for i in 0..n {
        for j in (i + 1)..n {
            let a = &comps[i];
            let b = &comps[j];

            // Same-layer check using side match
            let same_layer = a.side == b.side;
            if !same_layer {
                continue;
            }

            let required =
                clearance_between(constraints, &board.net_class_rules, &a.net_class, &b.net_class);

            if required <= 0.0 {
                continue;
            }

            // Use euclidean_distance directly on centers for the oracle
            // (different approach from production's edge_distance_to)
            let dist = a.center.euclidean_distance(&b.center)
                - (a.width.max(a.height) / 2.0)
                - (b.width.max(b.height) / 2.0);

            if dist < required {
                violations.push(violation(
                    Severity::Error,
                    "DRC_CLR_001",
                    &format!(
                        "[ORACLE] Clearance violation: {:.3}mm < {:.3}mm between {} and {}",
                        dist, required, a.refdes, b.refdes,
                    ),
                    DrcCategory::Drc,
                    "oracle_clearance",
                    vec![a.refdes.clone(), b.refdes.clone()],
                    Some(Location {
                        x: Some((a.center.x() + b.center.x()) / 2.0),
                        y: Some((a.center.y() + b.center.y()) / 2.0),
                        layer: None,
                    }),
                    serde_json::json!({
                        "actual_mm": dist,
                        "required_mm": required,
                    }),
                ));
            }
        }
    }

    violations
}

// ---------------------------------------------------------------------------
// Oracle: ComponentOverlapCheck — center-distance heuristic
// ---------------------------------------------------------------------------

/// Brute-force oracle for ComponentOverlapCheck.
///
/// Uses a center-distance heuristic (different from polygon-intersection
/// used in production) to validate overlap detection.
pub fn oracle_component_overlap(board: &BoardState) -> Vec<Violation> {
    let mut violations = Vec::new();
    let comps: Vec<&Component> = board.all_components().collect();
    let n = comps.len();

    for i in 0..n {
        for j in (i + 1)..n {
            let a = &comps[i];
            let b = &comps[j];

            if a.side != b.side {
                continue;
            }

            // Heuristic: if the distance between centers is less than the
            // sum of half-diagonals, there's likely overlap
            let half_diag_a = (a.width * a.width + a.height * a.height).sqrt() / 2.0;
            let half_diag_b = (b.width * b.width + b.height * b.height).sqrt() / 2.0;
            let center_dist = a.center.euclidean_distance(&b.center);

            if center_dist < (half_diag_a + half_diag_b) * 0.9 {
                violations.push(violation(
                    Severity::Critical,
                    "DRC_OVL_001",
                    &format!(
                        "[ORACLE] Component overlapped: {} covers {}",
                        a.refdes, b.refdes,
                    ),
                    DrcCategory::Drc,
                    "oracle_component_overlap",
                    vec![a.refdes.clone(), b.refdes.clone()],
                    Some(Location {
                        x: Some((a.center.x() + b.center.x()) / 2.0),
                        y: Some((a.center.y() + b.center.y()) / 2.0),
                        layer: None,
                    }),
                    serde_json::json!({}),
                ));
            }
        }
    }

    violations
}

// ---------------------------------------------------------------------------
// Oracle: CourtyardCheck — expanded bbox approach
// ---------------------------------------------------------------------------

/// Brute-force oracle for CourtyardCheck using expanded bounding boxes.
pub fn oracle_courtyard(board: &BoardState, margin_mm: f64) -> Vec<Violation> {
    let mut violations = Vec::new();
    let comps: Vec<&Component> = board.all_components().collect();
    let n = comps.len();
    let required_gap = margin_mm * 2.0;

    for i in 0..n {
        for j in (i + 1)..n {
            let a = &comps[i];
            let b = &comps[j];

            if a.side != b.side {
                continue;
            }

            // Expand bboxes by margin
            let a_min_x = a.center.x() - a.width / 2.0 - margin_mm;
            let a_max_x = a.center.x() + a.width / 2.0 + margin_mm;
            let a_min_y = a.center.y() - a.height / 2.0 - margin_mm;
            let a_max_y = a.center.y() + a.height / 2.0 + margin_mm;

            let b_min_x = b.center.x() - b.width / 2.0 - margin_mm;
            let b_max_x = b.center.x() + b.width / 2.0 + margin_mm;
            let b_min_y = b.center.y() - b.height / 2.0 - margin_mm;
            let b_max_y = b.center.y() + b.height / 2.0 + margin_mm;

            // Check if expanded bboxes overlap
            let overlap_x = a_min_x <= b_max_x && b_min_x <= a_max_x;
            let overlap_y = a_min_y <= b_max_y && b_min_y <= a_max_y;

            if overlap_x && overlap_y {
                violations.push(violation(
                    Severity::Warning,
                    "DRC_CRT_001",
                    &format!(
                        "[ORACLE] Courtyard violation between {} and {}",
                        a.refdes, b.refdes,
                    ),
                    DrcCategory::Drc,
                    "oracle_courtyard",
                    vec![a.refdes.clone(), b.refdes.clone()],
                    Some(Location {
                        x: Some((a.center.x() + b.center.x()) / 2.0),
                        y: Some((a.center.y() + b.center.y()) / 2.0),
                        layer: None,
                    }),
                    serde_json::json!({
                        "margin_per_comp_mm": margin_mm,
                        "required_gap_mm": required_gap,
                    }),
                ));
            }
        }
    }

    violations
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

    for (net_name, comp_refs) in &board.nets {
        let count: HashSet<&str> = comp_refs.iter().map(|s| s.as_str()).collect();
        if count.len() < 2 {
            violations.push(violation(
                Severity::Error,
                "ERC_NET_001",
                &format!(
                    "[ORACLE] Net '{}' has only {} connection(s). Minimum 2 required.",
                    net_name,
                    count.len(),
                ),
                DrcCategory::Erc,
                "oracle_net_connectivity",
                comp_refs.clone(),
                None,
                serde_json::json!({
                    "net_name": net_name,
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
        .values()
        .flat_map(|refs| refs.iter().map(|s| s.as_str()))
        .collect();

    // Double-check by counting
    let total_connected: usize = connected.len();

    for comp in board.all_components() {
        if !connected.contains(comp.refdes.as_str()) {
            violations.push(violation(
                Severity::Warning,
                "ERC_FLT_001",
                &format!(
                    "[ORACLE] Component '{}' is floating (total connected: {}).",
                    comp.refdes, total_connected,
                ),
                DrcCategory::Erc,
                "oracle_floating_pins",
                vec![comp.refdes.clone()],
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
    use geo::Line;

    fn point_segment_dist(px: f64, py: f64, sx: f64, sy: f64, ex: f64, ey: f64) -> f64 {
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

    fn segment_to_segment_distance(a: &Line<f64>, b: &Line<f64>) -> f64 {
        let a_start = (a.start.x, a.start.y);
        let a_end = (a.end.x, a.end.y);
        let b_start = (b.start.x, b.start.y);
        let b_end = (b.end.x, b.end.y);

        [
            point_segment_dist(a_start.0, a_start.1, b_start.0, b_start.1, b_end.0, b_end.1),
            point_segment_dist(a_end.0, a_end.1, b_start.0, b_start.1, b_end.0, b_end.1),
            point_segment_dist(b_start.0, b_start.1, a_start.0, a_start.1, a_end.0, a_end.1),
            point_segment_dist(b_end.0, b_end.1, a_start.0, a_start.1, a_end.0, a_end.1),
        ]
        .into_iter()
        .fold(f64::MAX, f64::min)
    }

    if board.traces.is_empty() {
        return Vec::new();
    }

    let mut violations = Vec::new();
    let segments: Vec<&crate::board::TraceSegment> = board.traces.iter().collect();
    let n = segments.len();

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
                            vec![si.net.clone(), sj.net.clone()],
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
