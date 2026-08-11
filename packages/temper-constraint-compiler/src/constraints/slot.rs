//! The compiled slot filter / scorer — the per-call hot path of
//! `ConstraintCompiler.compile_to_slot_filter()` / `compile_to_slot_scorer()`.
//!
//! The constraint set is compiled into a plain `ConstraintData` ONCE (at
//! `CompiledSlotFilter::new` / `CompiledSlotScorer::new`); every per-slot call
//! then evaluates against that pre-compiled data with no further Python
//! access — the "data moves into Rust" form (vs. `Py<PyAny>` handles).
//!
//! Placements are served through a lookup closure so the caller can choose
//! the cheapest source: the pyo3 layer passes a Python-dict-backed closure for
//! the per-call hot path (no marshalling), and tests pass a slice-backed one.

use crate::constraints::{
    centroid, distance, in_corridor_impl, in_zone, min_edge_distance, ConstraintData,
    DEFAULT_ESCAPE_CLEARANCE,
};

/// A per-placement lookup: exact-ref `placements[ref]` semantics.
pub type Lookup<'a> = dyn Fn(&str) -> Option<(f64, f64)> + 'a;
/// `compile_to_slot_filter()`: reject the slot iff any hard rule fires
/// (spacing, proximity, escape clearance, keep-clear corridor, required zone),
/// in the Python source's rule order with its early returns.
pub fn filter_slot(
    data: &ConstraintData,
    slot: (f64, f64),
    component: &str,
    lookup: &Lookup<'_>,
) -> bool {
    // 1. Component spacing rules (hard tier only).
    for rule in &data.spacing_rules {
        if rule.tier != "hard" {
            continue;
        }
        if component != rule.a && component != rule.b {
            continue;
        }
        let other = if component == rule.a { &rule.b } else { &rule.a };
        if let Some(pos) = lookup(other)
            && distance(slot, pos) < rule.min_separation_mm
        {
            return false;
        }
    }

    // 2. Proximity rules (hard mode) — must be close.
    for group in &data.groups {
        if !group.components.iter().any(|c| c == component) {
            continue;
        }
        for pr in &group.proximity_rules {
            if pr.tier != "hard" {
                continue;
            }
            if component != pr.a && component != pr.b {
                continue;
            }
            let other = if component == pr.a { &pr.b } else { &pr.a };
            if let Some(pos) = lookup(other)
                && distance(slot, pos) > pr.max_distance_mm
            {
                return false;
            }
        }
    }

    // 3. Escape clearances (hard mode).
    for ec in &data.escape_clearances {
        if ec.tier != "hard" {
            continue;
        }
        if let Some(pos) = lookup(&ec.component)
            && distance(slot, pos) < ec.clearance_mm.unwrap_or(DEFAULT_ESCAPE_CLEARANCE)
        {
            return false;
        }
    }

    // 4. Routing corridors (keep_clear + hard tier).
    for corridor in &data.corridors {
        if !corridor.keep_clear || corridor.tier != "hard" {
            continue;
        }
        if in_corridor_impl(slot, corridor, lookup) {
            return false;
        }
    }

    // 5. Zone membership (if a zone is required).
    if let Some(required_zone) = data.zone_for_component(component)
        && !required_zone.is_empty()
        && let Some(zone) = data.zones.iter().find(|z| z.name == required_zone)
        && !in_zone(slot, zone.bounds)
    {
        return false;
    }

    true
}

/// `compile_to_slot_scorer()`: accumulate non-negative penalties in the Python
/// source's rule order (each `+=` is one f64 add, in the same sequence).
pub fn score_slot(
    data: &ConstraintData,
    slot: (f64, f64),
    component: &str,
    lookup: &Lookup<'_>,
) -> f64 {
    let mut score = 0.0_f64;

    // 1. Proximity rules — prefer being close (soft tier only).
    for group in &data.groups {
        if !group.components.iter().any(|c| c == component) {
            continue;
        }
        for pr in &group.proximity_rules {
            if pr.tier != "soft" {
                continue;
            }
            if component != pr.a && component != pr.b {
                continue;
            }
            let other = if component == pr.a { &pr.b } else { &pr.a };
            if let Some(pos) = lookup(other) {
                let dist = distance(slot, pos);
                if dist > pr.max_distance_mm {
                    score += (dist - pr.max_distance_mm) * 10.0;
                }
            }
        }
    }

    // 2. Thermal edge preference.
    for thermal in &data.thermals {
        if !thermal.components.iter().any(|c| c == component) {
            continue;
        }
        if let Some(bounds) = data.board_bounds
            && thermal.prefer_edge
        {
            let edge_dist = min_edge_distance(slot, bounds);
            if edge_dist > thermal.max_distance_from_edge_mm {
                score += (edge_dist - thermal.max_distance_from_edge_mm) * 5.0;
            }
        }
    }

    // 3. Group spread — keep groups tight.
    for group in &data.groups {
        if !group.components.iter().any(|c| c == component) {
            continue;
        }
        let placed: Vec<(f64, f64)> = group
            .components
            .iter()
            .filter_map(|c| lookup(c))
            .collect();
        if !placed.is_empty() {
            let c = centroid(&placed);
            let dist = distance(slot, c);
            if dist > group.max_spread_mm / 2.0 {
                score += dist * group.weight * 0.1;
            }
        }
    }

    // 4. Component spacing rules (soft tier only in scorer).
    for rule in &data.spacing_rules {
        if rule.tier != "soft" {
            continue;
        }
        if component != rule.a && component != rule.b {
            continue;
        }
        let other = if component == rule.a { &rule.b } else { &rule.a };
        if let Some(pos) = lookup(other) {
            let dist = distance(slot, pos);
            if dist < rule.min_separation_mm {
                score += (rule.min_separation_mm - dist) * rule.weight;
            }
        }
    }

    // 5. Escape clearances (soft mode) — strong penalty for blocking escapes.
    for ec in &data.escape_clearances {
        if ec.tier != "soft" {
            continue;
        }
        if let Some(pos) = lookup(&ec.component)
            && distance(slot, pos) < ec.clearance_mm.unwrap_or(DEFAULT_ESCAPE_CLEARANCE)
        {
            score += 50.0;
        }
    }

    // 6. Routing corridors (soft mode).
    for corridor in &data.corridors {
        if corridor.tier != "soft" {
            continue;
        }
        if in_corridor_impl(slot, corridor, lookup) {
            let penalty = if corridor.keep_clear { 20.0 } else { 10.0 };
            score += penalty;
        }
    }

    score
}

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;
    use crate::constraints::{Corridor, Group, ProximityRule, SpacingRule};

    fn data() -> ConstraintData {
        ConstraintData {
            board_bounds: Some([0.0, 0.0, 100.0, 80.0]),
            spacing_rules: vec![SpacingRule {
                a: "A".into(),
                b: "B".into(),
                min_separation_mm: 10.0,
                tier: "hard".into(),
                weight: 1.0,
                description: String::new(),
            }],
            groups: vec![Group {
                name: "g".into(),
                components: vec!["C".into(), "D".into()],
                max_spread_mm: 30.0,
                zone: None,
                weight: 1.0,
                description: String::new(),
                proximity_rules: vec![ProximityRule {
                    a: "C".into(),
                    b: "D".into(),
                    max_distance_mm: 20.0,
                    tier: "soft".into(),
                    description: String::new(),
                }],
            }],
            escape_clearances: vec![],
            corridors: vec![Corridor {
                name: "path".into(),
                from_component: "J1".into(),
                to_component: "J2".into(),
                width_mm: 6.0,
                keep_clear: true,
                nets: vec![],
                tier: "hard".into(),
            }],
            thermals: vec![],
            zones: vec![],
            zone_assignments: vec![],
        }
    }

    fn lookup_from<'a>(placements: &'a [(&'a str, (f64, f64))]) -> impl Fn(&str) -> Option<(f64, f64)> + 'a {
        move |r| placements.iter().find(|(k, _)| *k == r).map(|(_, p)| *p)
    }

    #[cfg_attr(test, test)]
    fn hard_spacing_rejects_and_accepts() {
        let d = data();
        let p = [("A", (0.0, 0.0))];
        let lk = lookup_from(&p);
        assert!(!filter_slot(&d, (5.0, 0.0), "B", &lk));
        assert!(filter_slot(&d, (15.0, 0.0), "B", &lk));
    }

    #[cfg_attr(test, test)]
    fn soft_spacing_never_filters_but_scores() {
        let mut d = data();
        d.spacing_rules[0].tier = "soft".into();
        let p = [("A", (0.0, 0.0))];
        let lk = lookup_from(&p);
        assert!(filter_slot(&d, (5.0, 0.0), "B", &lk));
        // (10 - 5) * 1.0 = 5.0
        assert_eq!(score_slot(&d, (5.0, 0.0), "B", &lk), 5.0);
        assert_eq!(score_slot(&d, (15.0, 0.0), "B", &lk), 0.0);
    }

    #[cfg_attr(test, test)]
    fn corridor_blocks_inside_half_width() {
        let d = data();
        let p = [("J1", (0.0, 0.0)), ("J2", (20.0, 0.0))];
        let lk = lookup_from(&p);
        assert!(!filter_slot(&d, (10.0, 2.0), "X", &lk)); // 2 < 3
        assert!(filter_slot(&d, (10.0, 10.0), "X", &lk));
    }

    #[cfg_attr(test, test)]
    fn zone_required_rejects_outside() {
        let mut d = data();
        d.zones = vec![crate::constraints::ZoneData {
            name: "Z1".into(),
            bounds: [0.0, 0.0, 10.0, 10.0],
        }];
        d.zone_assignments = vec![("Q".into(), "Z1".into())];
        let lk = lookup_from(&[]);
        assert!(filter_slot(&d, (5.0, 5.0), "Q", &lk));
        assert!(!filter_slot(&d, (15.0, 5.0), "Q", &lk));
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("constraints::slot::tests::hard_spacing_rejects_and_accepts", hard_spacing_rejects_and_accepts),
        ("constraints::slot::tests::soft_spacing_never_filters_but_scores", soft_spacing_never_filters_but_scores),
        ("constraints::slot::tests::corridor_blocks_inside_half_width", corridor_blocks_inside_half_width),
        ("constraints::slot::tests::zone_required_rejects_outside", zone_required_rejects_outside),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}
