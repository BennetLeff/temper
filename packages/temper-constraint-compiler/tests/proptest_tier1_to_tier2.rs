use std::collections::HashMap;

use proptest::prelude::*;
use temper_constraint_compiler::desugar_tier1::compile_tier1_to_tier2;
use temper_constraint_compiler::ir_tier0::ConstraintTier;
use temper_constraint_compiler::ir_tier1::{
    Channel, ChannelTopology, ResolvedConstraint, ResolvedConstraintModel,
};
use temper_constraint_compiler::provenance::ProvenanceMap;
use temper_constraint_compiler::type_lattice::NetClassMetadata;

fn arb_channel_topology() -> impl Strategy<Value = ChannelTopology> {
    (1usize..5, 0.5f64..10.0f64, prop::sample::select(vec![
        "F.Cu".to_string(),
        "B.Cu".to_string(),
        "In1.Cu".to_string(),
        "In2.Cu".to_string(),
    ]))
        .prop_map(|(num_channels, width, layer)| {
            let mut channels = Vec::new();
            for i in 0..num_channels {
                let nets = (0..(num_channels % 4 + 1)).map(|j| i + j).collect();
                channels.push(Channel {
                    id: format!("CH{i}"),
                    width_mm: width + (i as f64),
                    nets,
                    layer: layer.clone(),
                });
            }
            ChannelTopology::new(channels)
        })
}

fn arb_separation_tier1(
    max_net: usize,
) -> impl Strategy<Value = ResolvedConstraint> {
    (0..max_net, 0..max_net, 0.1f64..10.0f64).prop_map(
        move |(net_a, net_b, min_dist)| ResolvedConstraint::Separation {
            id: format!("sep_{net_a}_{net_b}"),
            net_a,
            net_b,
            min_distance_mm: min_dist,
            tier: ConstraintTier::Hard,
            provenance: 0,
        },
    )
}

fn arb_layer_preference_tier1(
    max_net: usize,
) -> impl Strategy<Value = ResolvedConstraint> {
    (
        0..max_net,
        prop::sample::select(vec![
            "F.Cu", "B.Cu", "In1.Cu", "In2.Cu",
        ]),
    )
        .prop_map(move |(net, layer)| ResolvedConstraint::LayerPreference {
            id: format!("lp_{net}"),
            net,
            layer: layer.to_string(),
            tier: ConstraintTier::Hard,
            provenance: 1,
        })
}

proptest! {
    #[test]
    fn test_tier1_to_tier2_deterministic(
        (topology, separation) in (arb_channel_topology(), arb_separation_tier1(4))
    ) {
        let model = ResolvedConstraintModel::new(
            vec![separation.clone()],
            HashMap::new(),
        );
        let mut prov1 = ProvenanceMap::new();
        let result1 = compile_tier1_to_tier2(&model, &topology, &mut prov1);
        let mut prov2 = ProvenanceMap::new();
        let result2 = compile_tier1_to_tier2(&model, &topology, &mut prov2);

        if let (Ok(c1), Ok(c2)) = (&result1, &result2) {
            prop_assert_eq!(c1.len(), c2.len(),
                "deterministic: same separation constraint yields same number of ISA constraints");
        }
        prop_assert_eq!(
            result1.is_ok(), result2.is_ok(),
            "deterministic: both compilations should succeed or both fail"
        );
    }

    #[test]
    fn test_tier1_to_tier2_no_false_unsat(
        (topology, separation) in (arb_channel_topology(), arb_separation_tier1(4))
    ) {
        let model = ResolvedConstraintModel::new(
            vec![separation.clone()],
            HashMap::new(),
        );
        let mut prov = ProvenanceMap::new();
        let result = compile_tier1_to_tier2(&model, &topology, &mut prov);

        if topology.is_empty() {
            prop_assert!(result.is_err(), "empty topology should produce error");
        } else {
            if let Ok(constraints) = result {
                for c in &constraints {
                    if let temper_rust_router::types::InternalConstraint::LayerRestriction { var_name, allowed: false, .. } = c {
                        prop_assert!(!var_name.is_empty(), "LayerRestriction must have var_name");
                    }
                }
            }
        }
    }

    #[test]
    fn test_tier1_to_tier2_layer_preference(
        (topology, lp) in (arb_channel_topology(), arb_layer_preference_tier1(4))
    ) {
        let model = ResolvedConstraintModel::new(
            vec![lp.clone()],
            HashMap::new(),
        );
        let mut prov = ProvenanceMap::new();
        let result = compile_tier1_to_tier2(&model, &topology, &mut prov);

        if let Ok(constraints) = result {
            let layer_constraints: Vec<_> = constraints.iter()
                .filter(|c| matches!(c, temper_rust_router::types::InternalConstraint::LayerRestriction { .. }))
                .collect();
            if !layer_constraints.is_empty() {
                for c in &layer_constraints {
                    if let temper_rust_router::types::InternalConstraint::LayerRestriction { var_name, .. } = c {
                        prop_assert!(var_name.contains("uses_N"), "var_name should follow uses_N{{n}}_{{c}} pattern");
                    }
                }
            }
        }
    }

    #[test]
    fn test_tier1_to_tier2_no_panics(
        (topology, separation, lp) in (
            arb_channel_topology(),
            arb_separation_tier1(4),
            arb_layer_preference_tier1(4)
        )
    ) {
        let model = ResolvedConstraintModel::new(
            vec![separation, lp],
            HashMap::new(),
        );
        let mut prov = ProvenanceMap::new();
        let _result = compile_tier1_to_tier2(&model, &topology, &mut prov);
    }
}
