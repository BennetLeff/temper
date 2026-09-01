//! Pareto verdict for bounded regional PCB re-layout experiments.
//!
//! Measurement stays with the owning instruments (KiCad DRC, the exact
//! cross-domain pair oracle, and the Rust board parser).  This module owns the
//! acceptance contract: a creepage improvement can never buy a regression in
//! another safety category.

use std::collections::{BTreeMap, BTreeSet};

const HARD_VETO_DRC_RULES: &[&str] = &[
    "shorting_items",
    "clearance",
    "hole_clearance",
    "copper_edge_clearance",
];

#[derive(Debug, Clone, PartialEq)]
pub struct RegionalCandidateIdentity {
    pub ordinal: usize,
    pub candidate_id: String,
    pub placement_id: String,
    pub east_shift_mm: f64,
}

#[derive(Debug, Clone, PartialEq)]
pub struct PreRouteCandidateInput {
    pub k1_j1_gap_mm: f64,
    pub route_to_selv_gap_mm: f64,
    pub affected_safety_count: usize,
    pub new_safety_count: usize,
    pub worsened_safety_count: usize,
    pub new_body_overlap_count: usize,
    pub worsened_body_overlap_count: usize,
    pub new_courtyard_overlap_count: usize,
    pub worsened_courtyard_overlap_count: usize,
    pub containment_failure_count: usize,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PreRouteCandidateVerdict {
    pub accepted: bool,
    pub reasons: Vec<String>,
}

/// Apply the first-family pre-route vetoes in one canonical order.
pub fn evaluate_pre_route_candidate(input: &PreRouteCandidateInput) -> PreRouteCandidateVerdict {
    let mut reasons = Vec::new();
    if input.k1_j1_gap_mm < 13.1 {
        reasons.push("k1_j1".to_string());
    }
    if input.route_to_selv_gap_mm < 12.6 {
        reasons.push("route_to_selv".to_string());
    }
    if input.affected_safety_count > 0 {
        reasons.push("affected_safety".to_string());
    }
    if input.new_safety_count > 0 || input.worsened_safety_count > 0 {
        reasons.push("safety_regression".to_string());
    }
    if input.new_body_overlap_count > 0 || input.worsened_body_overlap_count > 0 {
        reasons.push("body_overlap".to_string());
    }
    if input.new_courtyard_overlap_count > 0 || input.worsened_courtyard_overlap_count > 0 {
        reasons.push("courtyard_overlap".to_string());
    }
    if input.containment_failure_count > 0 {
        reasons.push("containment".to_string());
    }
    PreRouteCandidateVerdict {
        accepted: reasons.is_empty(),
        reasons,
    }
}

/// Declare a finite first-family Cartesian product in a stable order.
///
/// The returned ordinal is the campaign identity. Board content hashes are
/// recorded after materialization; this function deliberately does not
/// pretend that an ordinal is a content digest.
pub fn declare_regional_candidates(
    mut placement_ids: Vec<String>,
    mut east_shifts_mm: Vec<f64>,
    placement_budget: usize,
) -> Result<Vec<RegionalCandidateIdentity>, String> {
    if placement_ids.is_empty() {
        return Err("at least one predecessor placement is required".into());
    }
    if east_shifts_mm.is_empty() {
        return Err("at least one east-shift template is required".into());
    }
    if placement_budget == 0 {
        return Err("placement budget must be positive".into());
    }
    if placement_ids.iter().any(|id| id.trim().is_empty()) {
        return Err("placement ids must be non-empty".into());
    }
    if east_shifts_mm.iter().any(|v| !v.is_finite() || *v <= 0.0) {
        return Err("east shifts must be finite and positive".into());
    }

    placement_ids.sort();
    east_shifts_mm.sort_by(f64::total_cmp);
    if placement_ids.windows(2).any(|w| w[0] == w[1]) {
        return Err("placement ids must be unique".into());
    }
    if east_shifts_mm.windows(2).any(|w| w[0] == w[1]) {
        return Err("east shifts must be unique".into());
    }

    let cardinality = placement_ids
        .len()
        .checked_mul(east_shifts_mm.len())
        .ok_or_else(|| "candidate cardinality overflow".to_string())?;
    if cardinality > placement_budget {
        return Err(format!(
            "declared candidate cardinality {cardinality} exceeds placement budget {placement_budget}"
        ));
    }

    let mut rows = Vec::with_capacity(cardinality);
    for placement_id in placement_ids {
        for east_shift_mm in &east_shifts_mm {
            let ordinal = rows.len() + 1;
            rows.push(RegionalCandidateIdentity {
                ordinal,
                candidate_id: format!("R14HV-{ordinal:03}"),
                placement_id: placement_id.clone(),
                east_shift_mm: *east_shift_mm,
            });
        }
    }
    Ok(rows)
}

#[derive(Debug, Clone, PartialEq)]
pub struct RegionalSnapshot {
    pub cross_domain_pairs: BTreeSet<String>,
    pub drc_errors_by_rule: BTreeMap<String, usize>,
    pub body_overlap_by_pair: BTreeMap<String, f64>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct RegionalVerdict {
    pub accepted: bool,
    pub improved: bool,
    pub reasons: Vec<String>,
    pub new_cross_domain_pairs: Vec<String>,
    pub removed_cross_domain_pairs: Vec<String>,
    pub drc_rule_deltas: BTreeMap<String, isize>,
    pub new_or_worsened_body_pairs: Vec<String>,
    pub routed_pad_endpoint_drift: Vec<String>,
}

pub fn routed_pad_endpoint_drift(
    baseline_pads: &[(String, f64, f64)],
    baseline_endpoints: &[(f64, f64)],
    candidate_pads: &[(String, f64, f64)],
    candidate_endpoints: &[(f64, f64)],
    tolerance_mm: f64,
) -> Vec<String> {
    fn connected(
        pads: &[(String, f64, f64)],
        endpoints: &[(f64, f64)],
        tolerance_mm: f64,
    ) -> BTreeSet<String> {
        let tol2 = tolerance_mm * tolerance_mm;
        pads.iter()
            .filter(|(_, x, y)| {
                endpoints.iter().any(|(ex, ey)| {
                    let dx = x - ex;
                    let dy = y - ey;
                    dx * dx + dy * dy <= tol2
                })
            })
            .map(|(id, _, _)| id.clone())
            .collect()
    }

    let before = connected(baseline_pads, baseline_endpoints, tolerance_mm);
    let after = connected(candidate_pads, candidate_endpoints, tolerance_mm);
    before.difference(&after).cloned().collect()
}

pub fn evaluate_regional_candidate(
    baseline: &RegionalSnapshot,
    candidate: &RegionalSnapshot,
    endpoint_drift: Vec<String>,
    instrument_errors: Vec<String>,
) -> RegionalVerdict {
    let new_pairs: Vec<_> = candidate
        .cross_domain_pairs
        .difference(&baseline.cross_domain_pairs)
        .cloned()
        .collect();
    let removed_pairs: Vec<_> = baseline
        .cross_domain_pairs
        .difference(&candidate.cross_domain_pairs)
        .cloned()
        .collect();

    let rules: BTreeSet<_> = baseline
        .drc_errors_by_rule
        .keys()
        .chain(candidate.drc_errors_by_rule.keys())
        .cloned()
        .collect();
    let drc_rule_deltas: BTreeMap<_, _> = rules
        .into_iter()
        .map(|rule| {
            let before = *baseline.drc_errors_by_rule.get(&rule).unwrap_or(&0);
            let after = *candidate.drc_errors_by_rule.get(&rule).unwrap_or(&0);
            (rule, after as isize - before as isize)
        })
        .collect();

    let new_or_worsened_body_pairs: Vec<_> = candidate
        .body_overlap_by_pair
        .iter()
        .filter_map(|(pair, after)| {
            let before = baseline.body_overlap_by_pair.get(pair).copied().unwrap_or(0.0);
            (*after > before + 1e-6).then(|| pair.clone())
        })
        .collect();

    let baseline_total: usize = baseline.drc_errors_by_rule.values().sum();
    let candidate_total: usize = candidate.drc_errors_by_rule.values().sum();
    let mut reasons = instrument_errors;
    if !new_pairs.is_empty() {
        reasons.push(format!("{} new HV<->SELV pair(s)", new_pairs.len()));
    }
    if candidate_total > baseline_total {
        reasons.push(format!(
            "total DRC findings rose from {baseline_total} to {candidate_total}"
        ));
    }
    for rule in HARD_VETO_DRC_RULES {
        if drc_rule_deltas.get(*rule).copied().unwrap_or(0) > 0 {
            reasons.push(format!("hard-veto DRC rule {rule} increased"));
        }
    }
    if !new_or_worsened_body_pairs.is_empty() {
        reasons.push(format!(
            "{} new or worsened F.Fab body collision(s)",
            new_or_worsened_body_pairs.len()
        ));
    }
    if !endpoint_drift.is_empty() {
        reasons.push(format!(
            "{} previously routed pad endpoint(s) lost connectivity",
            endpoint_drift.len()
        ));
    }

    let body_improved = baseline.body_overlap_by_pair.iter().any(|(pair, before)| {
        candidate.body_overlap_by_pair.get(pair).copied().unwrap_or(0.0) + 1e-6 < *before
    });
    let improved = !removed_pairs.is_empty() || candidate_total < baseline_total || body_improved;
    if !improved {
        reasons.push("candidate is non-regressing but does not improve any tracked axis".into());
    }

    RegionalVerdict {
        accepted: reasons.is_empty(),
        improved,
        reasons,
        new_cross_domain_pairs: new_pairs,
        removed_cross_domain_pairs: removed_pairs,
        drc_rule_deltas,
        new_or_worsened_body_pairs,
        routed_pad_endpoint_drift: endpoint_drift,
    }
}

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

    #[cfg_attr(test, test)]
    fn pre_route_verdict_owns_canonical_reason_order() {
        let verdict = evaluate_pre_route_candidate(&PreRouteCandidateInput {
            k1_j1_gap_mm: 12.0,
            route_to_selv_gap_mm: 11.0,
            affected_safety_count: 1,
            new_safety_count: 1,
            worsened_safety_count: 1,
            new_body_overlap_count: 1,
            worsened_body_overlap_count: 1,
            new_courtyard_overlap_count: 1,
            worsened_courtyard_overlap_count: 1,
            containment_failure_count: 1,
        });
        assert!(!verdict.accepted);
        assert_eq!(
            verdict.reasons,
            ["k1_j1", "route_to_selv", "affected_safety", "safety_regression",
             "body_overlap", "courtyard_overlap", "containment"]
        );
    }

    #[cfg_attr(test, test)]
    fn pre_route_verdict_accepts_only_an_empty_veto_set() {
        let verdict = evaluate_pre_route_candidate(&PreRouteCandidateInput {
            k1_j1_gap_mm: 13.1,
            route_to_selv_gap_mm: 12.6,
            affected_safety_count: 0,
            new_safety_count: 0,
            worsened_safety_count: 0,
            new_body_overlap_count: 0,
            worsened_body_overlap_count: 0,
            new_courtyard_overlap_count: 0,
            worsened_courtyard_overlap_count: 0,
            containment_failure_count: 0,
        });
        assert!(verdict.accepted);
        assert!(verdict.reasons.is_empty());
    }

    fn snapshot(pairs: &[&str], drc: &[(&str, usize)], bodies: &[(&str, f64)]) -> RegionalSnapshot {
        RegionalSnapshot {
            cross_domain_pairs: pairs.iter().map(|s| (*s).to_string()).collect(),
            drc_errors_by_rule: drc.iter().map(|(k, v)| ((*k).to_string(), *v)).collect(),
            body_overlap_by_pair: bodies.iter().map(|(k, v)| ((*k).to_string(), *v)).collect(),
        }
    }

    #[cfg_attr(test, test)]
    fn accepts_real_pareto_improvement() {
        let before = snapshot(&["A<->B", "C<->D"], &[("creepage", 10)], &[]);
        let after = snapshot(&["C<->D"], &[("creepage", 9)], &[]);
        let verdict = evaluate_regional_candidate(&before, &after, vec![], vec![]);
        assert!(verdict.accepted);
        assert!(verdict.improved);
    }

    #[cfg_attr(test, test)]
    fn rejects_creepage_win_that_buys_a_short() {
        let before = snapshot(&["A<->B"], &[("creepage", 10), ("shorting_items", 2)], &[]);
        let after = snapshot(&[], &[("creepage", 9), ("shorting_items", 3)], &[]);
        let verdict = evaluate_regional_candidate(&before, &after, vec![], vec![]);
        assert!(!verdict.accepted);
        assert!(verdict.reasons.iter().any(|r| r.contains("shorting_items")));
    }

    #[cfg_attr(test, test)]
    fn rejects_new_pair_even_when_counts_fall() {
        let before = snapshot(&["A<->B", "C<->D"], &[("creepage", 10)], &[]);
        let after = snapshot(&["C<->D", "E<->F"], &[("creepage", 9)], &[]);
        let verdict = evaluate_regional_candidate(&before, &after, vec![], vec![]);
        assert!(!verdict.accepted);
        assert_eq!(verdict.new_cross_domain_pairs, vec!["E<->F"]);
    }

    #[cfg_attr(test, test)]
    fn rejects_body_collision_endpoint_drift_and_instrument_error() {
        let before = snapshot(&["A<->B"], &[("creepage", 10)], &[("C1<->C2", 1.0)]);
        let after = snapshot(&[], &[("creepage", 9)], &[("C1<->C2", 1.1)]);
        let verdict = evaluate_regional_candidate(
            &before,
            &after,
            vec!["U1.1".into()],
            vec!["candidate DRC hit a reporting cap".into()],
        );
        assert!(!verdict.accepted);
        assert_eq!(verdict.reasons.len(), 3);
    }

    #[cfg_attr(test, test)]
    fn endpoint_drift_tracks_pad_identity_not_coordinate() {
        let before_pads = vec![("U1.1".into(), 1.0, 1.0)];
        let after_pads = vec![("U1.1".into(), 2.0, 1.0)];
        let endpoints = vec![(1.0, 1.0)];
        assert_eq!(
            routed_pad_endpoint_drift(&before_pads, &endpoints, &after_pads, &endpoints, 0.01),
            vec!["U1.1"]
        );
    }

    #[cfg_attr(test, test)]
    fn regional_declaration_is_deterministic_and_budgeted() {
        let a = declare_regional_candidates(
            vec!["C002".into(), "C001".into()],
            vec![5.5, 4.0, 5.0, 4.5],
            8,
        )
        .expect("valid bounded family");
        let b = declare_regional_candidates(
            vec!["C001".into(), "C002".into()],
            vec![4.0, 4.5, 5.0, 5.5],
            8,
        )
        .expect("input order must not matter");
        assert_eq!(a, b);
        assert_eq!(a.len(), 8);
        assert_eq!(a[0].candidate_id, "R14HV-001");
        assert_eq!(a[0].placement_id, "C001");
        assert_eq!(a[0].east_shift_mm, 4.0);
        assert!(declare_regional_candidates(vec!["C001".into()], vec![4.0, 4.5], 1).is_err());
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("regional_feasibility::tests::accepts_real_pareto_improvement", accepts_real_pareto_improvement),
        ("regional_feasibility::tests::rejects_creepage_win_that_buys_a_short", rejects_creepage_win_that_buys_a_short),
        ("regional_feasibility::tests::rejects_new_pair_even_when_counts_fall", rejects_new_pair_even_when_counts_fall),
        ("regional_feasibility::tests::rejects_body_collision_endpoint_drift_and_instrument_error", rejects_body_collision_endpoint_drift_and_instrument_error),
        ("regional_feasibility::tests::endpoint_drift_tracks_pad_identity_not_coordinate", endpoint_drift_tracks_pad_identity_not_coordinate),
        ("regional_feasibility::tests::regional_declaration_is_deterministic_and_budgeted", regional_declaration_is_deterministic_and_budgeted),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}
