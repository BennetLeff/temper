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
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}
