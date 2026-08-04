//! The constraint-satisfaction reporter — `ConstraintReporter.check()` plus
//! `ConstraintReport.to_text()` / `to_json()` shape logic, in Rust.
//!
//! Results are plain `CheckResult` values (status as the canonical string);
//! the pyo3 layer converts them to/from dicts. The `details` dict on a result
//! is opaque here (the shim passes it through for `to_json`).

use crate::constraints::{
    distance, min_edge_distance, point_to_segment_distance, py_float_str, py_max, py_min,
    ConstraintData, Corridor, EscapeClearance, Group, ProximityRule, SpacingRule, Thermal,
};

/// One checked constraint — mirrors the fields of `ConstraintResult` with
/// `status` as its canonical string value.
#[derive(Debug, Clone)]
pub struct CheckResult {
    pub ctype: String,
    pub status: String, // "satisfied" | "violated" | "warning" | "skipped"
    pub tier: String,
    pub components: Vec<String>,
    pub message: String,
    pub actual: Option<f64>,
    pub expected: Option<f64>,
}

impl CheckResult {
    pub fn is_violation(&self) -> bool {
        self.tier == "hard" && self.status == "violated"
    }
}

/// The summary block of `to_json()` — computed purely so the pyo3 layer only
/// has to copy numbers into dicts.
#[derive(Debug, Clone, Copy)]
pub struct ReportSummary {
    pub total: usize,
    pub hard_satisfied: usize,
    pub hard_total: usize,
    pub soft_satisfied: usize,
    pub soft_total: usize,
    pub violations: usize,
    pub warnings: usize,
}

pub fn report_summary(results: &[CheckResult]) -> ReportSummary {
    let hard_total = results.iter().filter(|r| r.tier == "hard").count();
    let soft_total = results.iter().filter(|r| r.tier == "soft").count();
    ReportSummary {
        total: results.len(),
        hard_satisfied: results
            .iter()
            .filter(|r| r.tier == "hard" && r.status == "satisfied")
            .count(),
        hard_total,
        soft_satisfied: results
            .iter()
            .filter(|r| r.tier == "soft" && r.status == "satisfied")
            .count(),
        soft_total,
        violations: results.iter().filter(|r| r.is_violation()).count(),
        warnings: results
            .iter()
            .filter(|r| r.tier == "soft" && r.status == "violated")
            .count(),
    }
}

/// `ConstraintReport.to_text()` — byte-identical string generation.
pub fn report_to_text(results: &[CheckResult]) -> String {
    let mut lines: Vec<String> = vec!["=== Constraint Satisfaction Report ===".to_string(), String::new()];

    let hard: Vec<&CheckResult> = results.iter().filter(|r| r.tier == "hard").collect();
    if !hard.is_empty() {
        lines.push("HARD CONSTRAINTS (must satisfy):".to_string());
        for result in &hard {
            let symbol = if result.status == "satisfied" { "✓" } else { "✗" };
            let annotation = if result.is_violation() { " ← VIOLATION" } else { "" };
            lines.push(format!("  {symbol} {}{annotation}", result.message));
        }
        lines.push(String::new());
    }

    let soft: Vec<&CheckResult> = results.iter().filter(|r| r.tier == "soft").collect();
    if !soft.is_empty() {
        lines.push("SOFT CONSTRAINTS (prefer):".to_string());
        for result in &soft {
            let symbol = if result.status == "satisfied" {
                "✓"
            } else if result.status == "violated" {
                "⚠"
            } else {
                "○"
            };
            lines.push(format!("  {symbol} {}", result.message));
        }
        lines.push(String::new());
    }

    lines.push("SUMMARY:".to_string());
    let summary = report_summary(results);
    if !hard.is_empty() {
        lines.push(format!(
            "  Hard: {}/{} satisfied",
            summary.hard_satisfied,
            hard.len()
        ));
    }
    if !soft.is_empty() {
        lines.push(format!(
            "  Soft: {}/{} satisfied",
            summary.soft_satisfied,
            soft.len()
        ));
    }
    if summary.violations > 0 {
        lines.push(format!("  VIOLATIONS: {}", summary.violations));
    }

    lines.join("\n")
}

/// `ConstraintReporter.check(placements)` — every check, in the Python
/// source's rule order: spacing rules, proximity rules (per group), thermals,
/// group spreads, escape clearances (1+ results each), corridors (1+ results).
pub fn check_all(
    data: &ConstraintData,
    placements: &[(String, (f64, f64))],
) -> Vec<CheckResult> {
    let mut out = Vec::new();
    for rule in &data.spacing_rules {
        out.push(check_spacing(rule, placements));
    }
    for group in &data.groups {
        for pr in &group.proximity_rules {
            out.push(check_proximity(pr, placements));
        }
    }
    for thermal in &data.thermals {
        out.push(check_thermal(thermal, placements, data.board_bounds));
    }
    for group in &data.groups {
        out.push(check_group_spread(group, placements));
    }
    for escape in &data.escape_clearances {
        out.extend(check_escape_clearance(escape, placements));
    }
    for corridor in &data.corridors {
        out.extend(check_routing_corridor(corridor, placements));
    }
    out
}

fn placed(placements: &[(String, (f64, f64))], ref_: &str) -> Option<(f64, f64)> {
    placements.iter().find(|(r, _)| r == ref_).map(|(_, p)| *p)
}

/// `_check_spacing`.
fn check_spacing(rule: &SpacingRule, placements: &[(String, (f64, f64))]) -> CheckResult {
    let a = &rule.a;
    let b = &rule.b;
    let pos_a = placed(placements, a);
    let pos_b = placed(placements, b);
    match (pos_a, pos_b) {
        (None, _) | (_, None) => CheckResult {
            ctype: "ComponentSpacing".to_string(),
            status: "skipped".to_string(),
            tier: rule.tier.clone(),
            components: vec![a.clone(), b.clone()],
            message: format!("ComponentSpacing: {a} - {b} (not placed)"),
            actual: None,
            expected: None,
        },
        (Some(pa), Some(pb)) => {
            let distance = distance(pa, pb);
            let satisfied = distance >= rule.min_separation_mm;
            let status = if satisfied { "satisfied" } else { "violated" };
            let op = if satisfied { '≥' } else { '<' };
            let message = format!(
                "ComponentSpacing: {a} - {b} ({distance:.1}mm {op} {}mm)",
                py_float_str(rule.min_separation_mm)
            );
            CheckResult {
                ctype: "ComponentSpacing".to_string(),
                status: status.to_string(),
                tier: rule.tier.clone(),
                components: vec![a.clone(), b.clone()],
                message,
                actual: Some(distance),
                expected: Some(rule.min_separation_mm),
            }
        }
    }
}

/// `_check_proximity`.
fn check_proximity(rule: &ProximityRule, placements: &[(String, (f64, f64))]) -> CheckResult {
    let a = &rule.a;
    let b = &rule.b;
    let pos_a = placed(placements, a);
    let pos_b = placed(placements, b);
    match (pos_a, pos_b) {
        (None, _) | (_, None) => CheckResult {
            ctype: "Proximity".to_string(),
            status: "skipped".to_string(),
            tier: rule.tier.clone(),
            components: vec![a.clone(), b.clone()],
            message: format!("Proximity: {a} - {b} (not placed)"),
            actual: None,
            expected: None,
        },
        (Some(pa), Some(pb)) => {
            let distance = distance(pa, pb);
            let satisfied = distance <= rule.max_distance_mm;
            let status = if satisfied { "satisfied" } else { "violated" };
            let op = if satisfied { '≤' } else { '>' };
            let message = format!(
                "Proximity: {a} - {b} ({distance:.1}mm {op} {}mm)",
                py_float_str(rule.max_distance_mm)
            );
            CheckResult {
                ctype: "Proximity".to_string(),
                status: status.to_string(),
                tier: rule.tier.clone(),
                components: vec![a.clone(), b.clone()],
                message,
                actual: Some(distance),
                expected: Some(rule.max_distance_mm),
            }
        }
    }
}

/// `_check_thermal` — first placed component only, always soft tier.
fn check_thermal(
    thermal: &Thermal,
    placements: &[(String, (f64, f64))],
    board_bounds: Option<[f64; 4]>,
) -> CheckResult {
    let placed_comps: Vec<&String> = thermal
        .components
        .iter()
        .filter(|c| placed(placements, c).is_some())
        .collect();

    let Some(comp) = placed_comps.first() else {
        return CheckResult {
            ctype: "Thermal".to_string(),
            status: "skipped".to_string(),
            tier: "soft".to_string(),
            components: thermal.components.clone(),
            message: format!("Thermal: {} (not placed)", thermal.components.join(", ")),
            actual: None,
            expected: None,
        };
    };

    if !thermal.prefer_edge || board_bounds.is_none() {
        return CheckResult {
            ctype: "Thermal".to_string(),
            status: "satisfied".to_string(),
            tier: "soft".to_string(),
            components: vec![(*comp).clone()],
            message: format!("Thermal: {comp} (no edge preference)"),
            actual: None,
            expected: None,
        };
    }

    let pos = placed(placements, comp);
    let (Some(edge_pos), Some(bounds)) = (pos, board_bounds) else {
        // Unreachable by the guards above, but the pyo3 boundary is not the
        // place to panic — mirror the source's contract instead.
        return CheckResult {
            ctype: "Thermal".to_string(),
            status: "satisfied".to_string(),
            tier: "soft".to_string(),
            components: vec![(*comp).clone()],
            message: format!("Thermal: {comp} (no edge preference)"),
            actual: None,
            expected: None,
        };
    };
    let edge_distance = min_edge_distance(edge_pos, bounds);
    let threshold = thermal.max_distance_from_edge_mm;
    let satisfied = edge_distance <= threshold;
    let status = if satisfied { "satisfied" } else { "violated" };
    let op = if satisfied { '≤' } else { '>' };
    let message = format!(
        "Thermal: {comp} edge distance ({edge_distance:.1}mm {op} {threshold:.1}mm preferred)"
    );
    CheckResult {
        ctype: "Thermal".to_string(),
        status: status.to_string(),
        tier: "soft".to_string(),
        components: vec![(*comp).clone()],
        message,
        actual: Some(edge_distance),
        expected: Some(threshold),
    }
}

/// `_check_group_spread` — bounding-box diagonal of the placed group members.
fn check_group_spread(group: &Group, placements: &[(String, (f64, f64))]) -> CheckResult {
    let placed_comps: Vec<&String> = group
        .components
        .iter()
        .filter(|c| placed(placements, c).is_some())
        .collect();

    if placed_comps.len() < 2 {
        return CheckResult {
            ctype: "GroupSpread".to_string(),
            status: "skipped".to_string(),
            tier: "soft".to_string(),
            components: group.components.clone(),
            message: format!("GroupSpread: {} (< 2 components placed)", group.name),
            actual: None,
            expected: None,
        };
    }

    let positions: Vec<(f64, f64)> = placed_comps
        .iter()
        .filter_map(|c| placed(placements, c))
        .collect();
    let xs: Vec<f64> = positions.iter().map(|p| p.0).collect();
    let ys: Vec<f64> = positions.iter().map(|p| p.1).collect();
    let width = py_max(&xs) - py_min(&xs);
    let height = py_max(&ys) - py_min(&ys);
    let diagonal = (width * width + height * height).sqrt();

    let satisfied = diagonal <= group.max_spread_mm;
    let status = if satisfied { "satisfied" } else { "violated" };
    let op = if satisfied { '≤' } else { '>' };
    let message = format!(
        "GroupSpread: {} ({diagonal:.1}mm {op} {}mm)",
        group.name,
        py_float_str(group.max_spread_mm)
    );
    CheckResult {
        ctype: "GroupSpread".to_string(),
        status: status.to_string(),
        tier: "soft".to_string(),
        components: placed_comps.iter().map(|c| (*c).clone()).collect(),
        message,
        actual: Some(diagonal),
        expected: Some(group.max_spread_mm),
    }
}

/// `_check_escape_clearance` — 1 result when clear/skipped, 1 per violation,
/// in placements dict iteration order.
fn check_escape_clearance(
    escape: &EscapeClearance,
    placements: &[(String, (f64, f64))],
) -> Vec<CheckResult> {
    let mut results = Vec::new();
    let comp = &escape.component;

    let Some(pos) = placed(placements, comp) else {
        results.push(CheckResult {
            ctype: "EscapeClearance".to_string(),
            status: "skipped".to_string(),
            tier: escape.tier.clone(),
            components: vec![comp.clone()],
            message: format!("EscapeClearance: {comp} (not placed)"),
            actual: None,
            expected: None,
        });
        return results;
    };

    let Some(clearance) = escape.clearance_mm else {
        results.push(CheckResult {
            ctype: "EscapeClearance".to_string(),
            status: "skipped".to_string(),
            tier: escape.tier.clone(),
            components: vec![comp.clone()],
            message: format!("EscapeClearance: {comp} (clearance not computed)"),
            actual: None,
            expected: None,
        });
        return results;
    };

    let mut violations: Vec<(String, f64)> = Vec::new();
    for (other_ref, other_pos) in placements {
        if other_ref == comp {
            continue;
        }
        let d = distance(pos, *other_pos);
        if d < clearance {
            violations.push((other_ref.clone(), d));
        }
    }

    if violations.is_empty() {
        results.push(CheckResult {
            ctype: "EscapeClearance".to_string(),
            status: "satisfied".to_string(),
            tier: escape.tier.clone(),
            components: vec![comp.clone()],
            message: format!("EscapeClearance: {comp} ({clearance:.1}mm zone clear)"),
            actual: None,
            expected: None,
        });
    } else {
        for (other_ref, d) in violations {
            let message = format!(
                "EscapeClearance: {other_ref} in {comp} zone ({d:.1}mm < {clearance:.1}mm)"
            );
            results.push(CheckResult {
                ctype: "EscapeClearance".to_string(),
                status: "violated".to_string(),
                tier: escape.tier.clone(),
                components: vec![comp.clone(), other_ref],
                message,
                actual: Some(d),
                expected: Some(clearance),
            });
        }
    }

    results
}

/// `_check_routing_corridor` — 1 result when clear/skipped, 1 per violation,
/// in placements dict iteration order.
fn check_routing_corridor(
    corridor: &Corridor,
    placements: &[(String, (f64, f64))],
) -> Vec<CheckResult> {
    let mut results = Vec::new();
    let from_comp = &corridor.from_component;
    let to_comp = &corridor.to_component;

    let pos_from = placed(placements, from_comp);
    let pos_to = placed(placements, to_comp);
    let (Some(pos_from), Some(pos_to)) = (pos_from, pos_to) else {
        results.push(CheckResult {
            ctype: "RoutingCorridor".to_string(),
            status: "skipped".to_string(),
            tier: corridor.tier.clone(),
            components: vec![from_comp.clone(), to_comp.clone()],
            message: format!("RoutingCorridor: {} (endpoints not placed)", corridor.name),
            actual: None,
            expected: None,
        });
        return results;
    };

    if !corridor.keep_clear {
        results.push(CheckResult {
            ctype: "RoutingCorridor".to_string(),
            status: "satisfied".to_string(),
            tier: corridor.tier.clone(),
            components: vec![from_comp.clone(), to_comp.clone()],
            message: format!(
                "RoutingCorridor: {} (no keep-clear requirement)",
                corridor.name
            ),
            actual: None,
            expected: None,
        });
        return results;
    }

    let half_width = corridor.width_mm / 2.0;

    let mut violations: Vec<(String, f64)> = Vec::new();
    for (other_ref, other_pos) in placements {
        if other_ref == from_comp || other_ref == to_comp {
            continue;
        }
        let d = point_to_segment_distance(*other_pos, pos_from, pos_to);
        if d < half_width {
            violations.push((other_ref.clone(), d));
        }
    }

    if violations.is_empty() {
        results.push(CheckResult {
            ctype: "RoutingCorridor".to_string(),
            status: "satisfied".to_string(),
            tier: corridor.tier.clone(),
            components: vec![from_comp.clone(), to_comp.clone()],
            message: format!(
                "RoutingCorridor: {} ({}mm corridor clear)",
                corridor.name,
                py_float_str(corridor.width_mm)
            ),
            actual: None,
            expected: None,
        });
    } else {
        for (other_ref, d) in violations {
            let message = format!(
                "RoutingCorridor: {other_ref} in {} path ({d:.1}mm < {half_width:.1}mm)",
                corridor.name
            );
            results.push(CheckResult {
                ctype: "RoutingCorridor".to_string(),
                status: "violated".to_string(),
                tier: corridor.tier.clone(),
                components: vec![from_comp.clone(), to_comp.clone(), other_ref],
                message,
                actual: Some(d),
                expected: Some(half_width),
            });
        }
    }

    results
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn empty_report_text_is_header_only() {
        // Python oracle: lines = [header, "", "SUMMARY:"], so the empty report
        // ends with a bare SUMMARY line (no counts, no sections).
        assert_eq!(
            report_to_text(&[]),
            "=== Constraint Satisfaction Report ===\n\nSUMMARY:"
        );
        let s = report_summary(&[]);
        assert_eq!((s.total, s.violations, s.warnings), (0, 0, 0));
    }

    #[test]
    fn spacing_check_statuses_and_message() {
        let rule = SpacingRule {
            a: "A".into(),
            b: "B".into(),
            min_separation_mm: 10.0,
            tier: "hard".into(),
            weight: 1.0,
            description: String::new(),
        };
        let placements = vec![
            ("A".to_string(), (0.0, 0.0)),
            ("B".to_string(), (15.0, 0.0)),
        ];
        let r = check_spacing(&rule, &placements);
        assert_eq!(r.status, "satisfied");
        assert_eq!(r.message, "ComponentSpacing: A - B (15.0mm ≥ 10.0mm)");
        assert_eq!(r.actual, Some(15.0));
        assert!(!r.is_violation());

        let placements = vec![
            ("A".to_string(), (0.0, 0.0)),
            ("B".to_string(), (5.0, 0.0)),
        ];
        let r = check_spacing(&rule, &placements);
        assert_eq!(r.status, "violated");
        assert!(r.is_violation());
    }

    #[test]
    fn thermal_skipped_when_none_placed() {
        let t = Thermal {
            components: vec!["Q1".into(), "Q2".into()],
            prefer_edge: true,
            max_distance_from_edge_mm: 10.0,
            min_spacing_mm: 5.0,
            description: String::new(),
        };
        let r = check_thermal(&t, &[], Some([0.0, 0.0, 100.0, 100.0]));
        assert_eq!(r.status, "skipped");
        assert_eq!(r.message, "Thermal: Q1, Q2 (not placed)");
        assert_eq!(r.components, vec!["Q1", "Q2"]);
    }
}
