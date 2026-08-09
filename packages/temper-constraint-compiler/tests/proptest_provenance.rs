use proptest::prelude::*;
use temper_constraint_compiler::ir_tier0::ConstraintTier;
use temper_constraint_compiler::provenance::{ProvenanceMap, ProvenanceRef, reverse_map_unsat_core};

proptest! {
    // -----------------------------------------------------------------
    // ProvenanceMap::push / get — round-trip
    // -----------------------------------------------------------------

    /// P1. push returns a reference that get retrieves correctly,
    /// preserving all six fields.
    #[test]
    fn p1_push_get_round_trip(
        pcl_id in "[a-z0-9_]{4,12}",
        t0_type in "[A-Z][a-z]{4,12}",
        rule_t0 in "[a-z_]{6,16}",
        rule_t1 in "[a-z_]{6,16}",
        rationale in "[A-Za-z ]{4,20}",
        tier in prop_oneof![Just(ConstraintTier::Hard), Just(ConstraintTier::Soft)],
    ) {
        let mut prov = ProvenanceMap::new();
        let idx = prov.push(
            pcl_id.clone(),
            t0_type.clone(),
            rule_t0.clone(),
            rule_t1.clone(),
            rationale.clone(),
            tier,
        );
        let entry = prov.get(idx);
        prop_assert!(entry.is_some());
        #[allow(clippy::unwrap_used)]
        let e = entry.unwrap();
        prop_assert_eq!(&e.pcl_constraint_id, &pcl_id);
        prop_assert_eq!(&e.tier0_type, &t0_type);
        prop_assert_eq!(&e.desugar_rule_t0, &rule_t0);
        prop_assert_eq!(&e.desugar_rule_t1, &rule_t1);
        prop_assert_eq!(&e.rationale, &rationale);
        prop_assert_eq!(e.tier, tier);
    }

    /// P2. Sequential pushes yield monotonically increasing indices.
    #[test]
    fn p2_push_indices_monotonic(
        count in 1usize..=20,
    ) {
        let mut prov = ProvenanceMap::new();
        let mut prev: Option<ProvenanceRef> = None;
        for i in 0..count {
            let idx = prov.push(
                format!("pcl_{i}"),
                "Adjacent".into(),
                "r0".into(),
                "r1".into(),
                "reason".into(),
                ConstraintTier::Hard,
            );
            if let Some(p) = prev {
                prop_assert!(idx > p);
            }
            prev = Some(idx);
        }
    }

    /// P3. get with an out-of-bounds index returns None.
    #[test]
    fn p3_get_out_of_bounds_returns_none(
        count in 0usize..=10,
    ) {
        let mut prov = ProvenanceMap::new();
        for i in 0..count {
            prov.push(
                format!("pcl_{i}"),
                "Adjacent".into(),
                "r0".into(),
                "r1".into(),
                "test".into(),
                ConstraintTier::Hard,
            );
        }
        let n = prov.entries.len();
        prop_assert!(prov.get(n).is_none());
        prop_assert!(prov.get(n + 1000).is_none());
    }

    /// P4. link_clause then reverse_map_unsat_core with that clause
    /// yields at least one diagnostic.
    #[test]
    fn p4_link_clause_then_reverse_map(
        count in 1usize..=10,
    ) {
        let mut prov = ProvenanceMap::new();
        let mut refs = Vec::new();
        for i in 0..count {
            let idx = prov.push(
                format!("pcl_{i}"),
                "Adjacent".into(),
                "r0".into(),
                "r1".into(),
                "reason".into(),
                ConstraintTier::Hard,
            );
            refs.push(idx);
        }

        for (clause_idx, &r) in refs.iter().enumerate() {
            prov.link_clause(clause_idx, r);
        }

        let core: Vec<usize> = (0..refs.len()).collect();
        let diags = reverse_map_unsat_core(&core, &prov);
        prop_assert!(!diags.is_empty());
        prop_assert!(diags.len() <= count);
    }

    /// P5. Empty unsat core produces empty diagnostics.
    #[test]
    fn p5_empty_core_empty_diagnostics(
        count in 0usize..=10,
    ) {
        let mut prov = ProvenanceMap::new();
        for i in 0..count {
            let idx = prov.push(
                format!("pcl_{i}"),
                "Adjacent".into(),
                "r0".into(),
                "r1".into(),
                "test".into(),
                ConstraintTier::Hard,
            );
            prov.link_clause(i, idx);
        }
        let diags = reverse_map_unsat_core(&[], &prov);
        prop_assert!(diags.is_empty());
    }
}
