use std::collections::HashMap;

use proptest::prelude::*;
use temper_constraint_compiler::desugar_tier0::compile_tier0_to_tier1;
use temper_constraint_compiler::ir_tier0::{ConstraintTier, PclConstraint, PclConstraintModel, Rect};
use temper_constraint_compiler::ir_tier1::{ComponentResolver, ZoneResolver};
use temper_constraint_compiler::provenance::ProvenanceMap;

struct TestResolver {
    component_map: HashMap<String, usize>,
    zone_map: HashMap<String, Rect>,
}

impl ComponentResolver for TestResolver {
    fn resolve(&self, component_ref: &str) -> Option<usize> {
        self.component_map.get(component_ref).copied()
    }
}

impl ZoneResolver for TestResolver {
    fn resolve(&self, zone_name: &str) -> Option<Rect> {
        self.zone_map.get(zone_name).copied()
    }
}

fn arb_component_name() -> impl Strategy<Value = String> {
    prop::sample::select(vec![
        "Q1".to_string(),
        "Q2".to_string(),
        "D1".to_string(),
        "D2".to_string(),
        "C1".to_string(),
        "R1".to_string(),
        "MCU".to_string(),
        "SENSOR".to_string(),
        "CONN1".to_string(),
        "U1".to_string(),
    ])
}

fn arb_tier() -> impl Strategy<Value = ConstraintTier> {
    prop_oneof![
        Just(ConstraintTier::Hard),
        Just(ConstraintTier::Strong),
        Just(ConstraintTier::Soft),
    ]
}

fn arb_adjacent() -> impl Strategy<Value = PclConstraint> {
    (
        arb_component_name(),
        arb_component_name(),
        0.1f64..100.0f64,
        arb_tier(),
    )
        .prop_map(|(a, b, max_dist, tier)| PclConstraint::Adjacent {
            id: format!("adj_{a}_{b}"),
            a,
            b,
            max_distance_mm: max_dist,
            tier,
            because: "proptest".into(),
            metric: None,
            pin_a: None,
            pin_b: None,
        })
}

fn arb_separated() -> impl Strategy<Value = PclConstraint> {
    (
        arb_component_name(),
        arb_component_name(),
        0.1f64..100.0f64,
        arb_tier(),
    )
        .prop_map(|(a, b, min_dist, tier)| PclConstraint::Separated {
            id: format!("sep_{a}_{b}"),
            a,
            b,
            min_distance_mm: min_dist,
            tier,
            because: "proptest".into(),
            metric: None,
        })
}

fn arb_inferred() -> impl Strategy<Value = PclConstraint> {
    (
        arb_component_name(),
        arb_component_name(),
        0.1f64..100.0f64,
        arb_tier(),
        prop::option::of("B\\.Cu|F\\.Cu|In1\\.Cu|In2\\.Cu"),
    )
        .prop_map(
            |(a, b, clearance, tier, layer_restriction)| PclConstraint::InferredSeparation {
                id: format!("inf_{a}_{b}"),
                source_pair: (a, b),
                clearance_floor_mm: clearance,
                layer_restriction,
                tier,
                because: "proptest lattice inference".into(),
            },
        )
}

fn arb_pcl_constraint() -> impl Strategy<Value = PclConstraint> {
    prop_oneof![arb_adjacent(), arb_separated(), arb_inferred()]
}

proptest! {
    #[test]
    fn test_tier0_to_tier1_deterministic(
        constraints in prop::collection::vec(arb_pcl_constraint(), 1..10)
    ) {
        let model = PclConstraintModel::new(constraints, vec![]);
        let component_names: Vec<String> = model.all_constraints()
            .filter_map(|c| match c {
                PclConstraint::Adjacent { a, b, .. } => Some(vec![a.clone(), b.clone()]),
                PclConstraint::Separated { a, b, .. } => Some(vec![a.clone(), b.clone()]),
                PclConstraint::InferredSeparation { source_pair, .. } => Some(vec![source_pair.0.clone(), source_pair.1.clone()]),
                _ => None,
            })
            .flatten()
            .collect();

        let mut comp_map = HashMap::new();
        for (i, name) in component_names.iter().enumerate() {
            comp_map.insert(name.clone(), i);
        }
        let zone_map: HashMap<String, Rect> = HashMap::new();

        let resolver = TestResolver { component_map: comp_map, zone_map };

        let mut prov1 = ProvenanceMap::new();
        let result1 = compile_tier0_to_tier1(
            &model, &resolver, &resolver, &mut prov1,
        );

        let mut prov2 = ProvenanceMap::new();
        let result2 = compile_tier0_to_tier1(
            &model, &resolver, &resolver, &mut prov2,
        );

        if let (Ok(m1), Ok(m2)) = (&result1, &result2) {
            assert_eq!(m1.constraints.len(), m2.constraints.len(),
                "deterministic: same input should yield same number of constraints");
        }

        prop_assert_eq!(
            result1.is_ok(), result2.is_ok(),
            "deterministic: both compilations should succeed or both fail"
        );
    }

    #[test]
    fn test_tier0_to_tier1_provenance_valid(
        constraints in prop::collection::vec(arb_pcl_constraint(), 1..5)
    ) {
        let model = PclConstraintModel::new(constraints, vec![]);
        let component_names: Vec<String> = model.all_constraints()
            .filter_map(|c| match c {
                PclConstraint::Adjacent { a, b, .. } => Some(vec![a.clone(), b.clone()]),
                PclConstraint::Separated { a, b, .. } => Some(vec![a.clone(), b.clone()]),
                PclConstraint::InferredSeparation { source_pair, .. } => Some(vec![source_pair.0.clone(), source_pair.1.clone()]),
                _ => None,
            })
            .flatten()
            .collect();

        let mut comp_map = HashMap::new();
        for (i, name) in component_names.iter().enumerate() {
            comp_map.insert(name.clone(), i);
        }
        let zone_map: HashMap<String, Rect> = HashMap::new();
        let resolver = TestResolver { component_map: comp_map, zone_map };

        let mut prov = ProvenanceMap::new();
        if let Ok(resolved_model) = compile_tier0_to_tier1(&model, &resolver, &resolver, &mut prov) {
            for constraint in &resolved_model.constraints {
                let prov_ref = constraint.provenance();
                assert!(
                    prov.get(prov_ref).is_some(),
                    "every ResolvedConstraint should have a valid ProvenanceRef"
                );
            }
        }
    }

    #[test]
    fn test_tier0_to_tier1_produces_at_least_one(
        constraints in prop::collection::vec(arb_pcl_constraint(), 1..3)
    ) {
        let model = PclConstraintModel::new(constraints, vec![]);
        let component_names: Vec<String> = model.all_constraints()
            .filter_map(|c| match c {
                PclConstraint::Adjacent { a, b, .. } => Some(vec![a.clone(), b.clone()]),
                PclConstraint::Separated { a, b, .. } => Some(vec![a.clone(), b.clone()]),
                PclConstraint::InferredSeparation { source_pair, .. } => Some(vec![source_pair.0.clone(), source_pair.1.clone()]),
                _ => None,
            })
            .flatten()
            .collect();

        let mut comp_map = HashMap::new();
        for (i, name) in component_names.iter().enumerate() {
            comp_map.insert(name.clone(), i);
        }
        let zone_map: HashMap<String, Rect> = HashMap::new();
        let resolver = TestResolver { component_map: comp_map, zone_map };

        let mut prov = ProvenanceMap::new();
        if let Ok(resolved_model) = compile_tier0_to_tier1(&model, &resolver, &resolver, &mut prov) {
            assert!(
                resolved_model.constraints.len() >= model.all_constraints().count(),
                "each PCL constraint should produce at least 1 ResolvedConstraint"
            );
        }
    }

    #[test]
    fn test_tier0_to_tier1_no_panics_on_valid_input(
        constraints in prop::collection::vec(arb_pcl_constraint(), 0..20)
    ) {
        let model = PclConstraintModel::new(constraints, vec![]);

        let mut comp_map = HashMap::new();
        for (i, name) in [
            "Q1", "Q2", "D1", "D2", "C1", "R1", "MCU", "SENSOR", "CONN1", "U1",
        ].iter().enumerate() {
            comp_map.insert(name.to_string(), i);
        }
        let zone_map: HashMap<String, Rect> = HashMap::new();
        let resolver = TestResolver { component_map: comp_map, zone_map };

        let mut prov = ProvenanceMap::new();
        let _result = compile_tier0_to_tier1(&model, &resolver, &resolver, &mut prov);
    }
}
