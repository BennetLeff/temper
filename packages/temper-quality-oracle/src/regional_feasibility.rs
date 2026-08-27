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

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct BlockTranslation {
    pub dx_mm: f64,
    pub dy_mm: f64,
    pub ring: usize,
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct BlockSearchMove {
    pub arrangement_index: usize,
    pub block_quarter_turn: usize,
    pub translation: BlockTranslation,
}

#[derive(Debug, Clone, PartialEq)]
pub struct RoutedBlockCandidate {
    pub candidate_id: usize,
    pub translation: BlockTranslation,
    pub accepted: bool,
    pub removed_cross_domain_pairs: usize,
    pub drc_errors: usize,
    pub pad_connected_nets: usize,
    pub unrouted_nets: usize,
}

/// Finite rigid-block translations, ordered by Chebyshev ring.  The origin is
/// excluded so router budget is never spent on the unchanged board.
pub fn block_translation_schedule(
    step_mm: f64,
    max_rings: usize,
    max_candidates: usize,
) -> Result<Vec<BlockTranslation>, String> {
    if !step_mm.is_finite() || step_mm <= 0.0 {
        return Err("step_mm must be finite and > 0".into());
    }
    if max_rings == 0 || max_candidates == 0 {
        return Err("max_rings and max_candidates must be > 0".into());
    }
    let mut out = Vec::with_capacity(max_candidates);
    macro_rules! push {
        ($x:expr, $y:expr, $ring:expr) => {{
            out.push(BlockTranslation {
                dx_mm: $x as f64 * step_mm,
                dy_mm: $y as f64 * step_mm,
                ring: $ring,
            });
            if out.len() == max_candidates { return Ok(out); }
        }};
    }
    for ring in 1..=max_rings {
        let r = ring as isize;
        for x in -r..=r { push!(x, -r, ring); }
        for y in (-r + 1)..=r { push!(r, y, ring); }
        for x in (-r..r).rev() { push!(x, r, ring); }
        for y in ((-r + 1)..r).rev() { push!(-r, y, ring); }
    }
    Ok(out)
}

/// Compose internal arrangements, whole-block rotations, and translations
/// into one deterministic finite vocabulary. Arrangement zero is the as-is
/// layout; only its unchanged origin/rotation tuple is excluded.
pub fn block_search_schedule(
    step_mm: f64,
    max_rings: usize,
    arrangement_count: usize,
    block_quarter_turns: &[usize],
    max_candidates: usize,
) -> Result<Vec<BlockSearchMove>, String> {
    if arrangement_count == 0 || block_quarter_turns.is_empty() || max_candidates == 0 {
        return Err("arrangements, rotations, and max_candidates must be non-empty".into());
    }
    if block_quarter_turns.iter().any(|turn| *turn > 3) {
        return Err("block quarter turns must be in 0..=3".into());
    }
    let side = max_rings
        .checked_mul(2)
        .and_then(|value| value.checked_add(1))
        .ok_or_else(|| "max_rings is too large".to_string())?;
    let translation_count = side
        .checked_mul(side)
        .and_then(|value| value.checked_sub(1))
        .ok_or_else(|| "max_rings is too large".to_string())?;
    let translations = block_translation_schedule(
        step_mm,
        max_rings,
        translation_count.min(max_candidates),
    )?;
    let origin = BlockTranslation { dx_mm: 0.0, dy_mm: 0.0, ring: 0 };
    let mut out = Vec::with_capacity(max_candidates);
    for translation in std::iter::once(origin).chain(translations) {
        for arrangement_index in 0..arrangement_count {
            for &block_quarter_turn in block_quarter_turns {
                if translation.ring == 0 && arrangement_index == 0 && block_quarter_turn == 0 {
                    continue;
                }
                out.push(BlockSearchMove {
                    arrangement_index,
                    block_quarter_turn,
                    translation,
                });
                if out.len() == max_candidates {
                    return Ok(out);
                }
            }
        }
    }
    Ok(out)
}

/// Full safety acceptance is a prerequisite; routed connectivity dominates
/// the secondary quality axes among the remaining candidates.
pub fn select_routed_block_candidate(
    candidates: &[RoutedBlockCandidate],
) -> Option<RoutedBlockCandidate> {
    candidates.iter().filter(|c| c.accepted).min_by(|a, b| {
        b.pad_connected_nets.cmp(&a.pad_connected_nets)
            .then_with(|| a.unrouted_nets.cmp(&b.unrouted_nets))
            .then_with(|| b.removed_cross_domain_pairs.cmp(&a.removed_cross_domain_pairs))
            .then_with(|| a.drc_errors.cmp(&b.drc_errors))
            .then_with(|| a.translation.ring.cmp(&b.translation.ring))
            .then_with(|| a.candidate_id.cmp(&b.candidate_id))
    }).cloned()
}

/// Convert collision feedback into deterministic block-expansion candidates.
pub fn block_expansion_candidates(
    block_refs: &[String],
    collision_pairs: &[String],
) -> Vec<(String, usize)> {
    let block: BTreeSet<_> = block_refs.iter().map(String::as_str).collect();
    let mut counts: BTreeMap<String, usize> = BTreeMap::new();
    for pair in collision_pairs {
        let Some((left, right)) = pair.split_once("<->") else { continue };
        let outside = match (block.contains(left), block.contains(right)) {
            (true, false) => Some(right),
            (false, true) => Some(left),
            _ => None,
        };
        if let Some(reference) = outside {
            *counts.entry(reference.to_string()).or_default() += 1;
        }
    }
    let mut result: Vec<_> = counts.into_iter().collect();
    result.sort_by(|(ra, ca), (rb, cb)| cb.cmp(ca).then_with(|| ra.cmp(rb)));
    result
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

    #[cfg_attr(test, test)]
    fn translation_schedule_is_finite_and_excludes_origin() {
        let schedule = block_translation_schedule(5.0, 3, 10).unwrap();
        assert_eq!(schedule.len(), 10);
        assert_eq!(schedule[0], BlockTranslation { dx_mm: -5.0, dy_mm: -5.0, ring: 1 });
        assert!(schedule.iter().all(|p| p.dx_mm != 0.0 || p.dy_mm != 0.0));
        assert_eq!(schedule, block_translation_schedule(5.0, 3, 10).unwrap());
    }

    #[cfg_attr(test, test)]
    fn translation_schedule_rejects_invalid_requests() {
        assert!(block_translation_schedule(0.0, 1, 1).is_err());
        assert!(block_translation_schedule(f64::NAN, 1, 1).is_err());
        assert!(block_translation_schedule(1.0, 0, 1).is_err());
        assert!(block_translation_schedule(1.0, 1, 0).is_err());
    }

    #[cfg_attr(test, test)]
    fn structural_schedule_is_finite_origin_first_and_excludes_unchanged() {
        let schedule = block_search_schedule(10.0, 1, 3, &[0, 1], 8).unwrap();
        assert_eq!(schedule.len(), 8);
        assert_eq!(schedule[0].arrangement_index, 0);
        assert_eq!(schedule[0].block_quarter_turn, 1);
        assert_eq!(schedule[0].translation.ring, 0);
        assert_eq!(schedule[1].arrangement_index, 1);
        assert!(schedule.iter().all(|item| {
            item.arrangement_index != 0
                || item.block_quarter_turn != 0
                || item.translation.ring != 0
        }));
    }

    #[cfg_attr(test, test)]
    fn structural_schedule_rejects_unbounded_or_invalid_vocabulary() {
        assert!(block_search_schedule(10.0, 1, 0, &[0], 1).is_err());
        assert!(block_search_schedule(10.0, 1, 1, &[], 1).is_err());
        assert!(block_search_schedule(10.0, 1, 1, &[4], 1).is_err());
        assert!(block_search_schedule(10.0, 1, 1, &[0], 0).is_err());
    }

    fn routed(id: usize, accepted: bool, connected: usize, removed: usize) -> RoutedBlockCandidate {
        RoutedBlockCandidate {
            candidate_id: id,
            translation: BlockTranslation { dx_mm: id as f64, dy_mm: 0.0, ring: id },
            accepted,
            removed_cross_domain_pairs: removed,
            drc_errors: 405,
            pad_connected_nets: connected,
            unrouted_nets: 1,
        }
    }

    #[cfg_attr(test, test)]
    fn selector_never_accepts_unsafe_candidate() {
        let unsafe_complete = routed(1, false, 100, 20);
        let safe = routed(2, true, 90, 2);
        assert_eq!(select_routed_block_candidate(&[unsafe_complete, safe]).unwrap().candidate_id, 2);
    }

    #[cfg_attr(test, test)]
    fn selector_prioritizes_connectivity_then_safety_improvement() {
        let incomplete = routed(1, true, 89, 20);
        let complete = routed(2, true, 90, 2);
        let safer_complete = routed(3, true, 90, 3);
        assert_eq!(select_routed_block_candidate(&[incomplete, complete, safer_complete]).unwrap().candidate_id, 3);
    }

    #[cfg_attr(test, test)]
    fn expansion_feedback_names_only_external_blockers() {
        let block = vec!["R4".into(), "C4".into()];
        let pairs = vec!["C4<->R8".into(), "C4<->R46".into(), "R4<->R8".into(), "C4<->R4".into()];
        assert_eq!(block_expansion_candidates(&block, &pairs), vec![("R8".into(), 2), ("R46".into(), 1)]);
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
        ("regional_feasibility::tests::translation_schedule_is_finite_and_excludes_origin", translation_schedule_is_finite_and_excludes_origin),
        ("regional_feasibility::tests::translation_schedule_rejects_invalid_requests", translation_schedule_rejects_invalid_requests),
        ("regional_feasibility::tests::structural_schedule_is_finite_origin_first_and_excludes_unchanged", structural_schedule_is_finite_origin_first_and_excludes_unchanged),
        ("regional_feasibility::tests::structural_schedule_rejects_unbounded_or_invalid_vocabulary", structural_schedule_rejects_unbounded_or_invalid_vocabulary),
        ("regional_feasibility::tests::selector_never_accepts_unsafe_candidate", selector_never_accepts_unsafe_candidate),
        ("regional_feasibility::tests::selector_prioritizes_connectivity_then_safety_improvement", selector_prioritizes_connectivity_then_safety_improvement),
        ("regional_feasibility::tests::expansion_feedback_names_only_external_blockers", expansion_feedback_names_only_external_blockers),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}
