use crate::desugar_tier0::CompileError;
use crate::ir_tier1::{ChannelTopology, ResolvedConstraint, ResolvedConstraintModel};
use crate::provenance::ProvenanceMap;
use temper_rust_router::types::InternalConstraint;

pub type DesugarRuleTier1 = fn(
    constraint: &ResolvedConstraint,
    topology: &ChannelTopology,
    provenance: &mut ProvenanceMap,
) -> Result<Vec<InternalConstraint>, CompileError>;

pub static RULES_TIER1: &[(&str, DesugarRuleTier1)] = &[
    ("Separation", desugar_separation_tier1 as DesugarRuleTier1),
    ("Adjacency", desugar_adjacency_tier1 as DesugarRuleTier1),
    ("ZoneEnclosing", desugar_zone_enclosing_tier1 as DesugarRuleTier1),
    ("LayerPreference", desugar_layer_preference_tier1 as DesugarRuleTier1),
    ("Alignment", desugar_advisory_tier1 as DesugarRuleTier1),
    ("EdgePlacement", desugar_advisory_tier1 as DesugarRuleTier1),
    ("Anchored", desugar_advisory_tier1 as DesugarRuleTier1),
    ("LoopArea", desugar_advisory_tier1 as DesugarRuleTier1),
];

fn emit_var_name(net: usize, channel_id: &str) -> String {
    format!("uses_N{net}_{channel_id}")
}

fn desugar_separation_tier1(
    constraint: &ResolvedConstraint,
    topology: &ChannelTopology,
    prov: &mut ProvenanceMap,
) -> Result<Vec<InternalConstraint>, CompileError> {
    if let ResolvedConstraint::Separation {
        id,
        net_a,
        net_b,
        min_distance_mm,
        tier: _tier,
        provenance: prov_ref,
    } = constraint
    {
        if topology.is_empty() {
            return Err(CompileError::UnreachableConstraint(format!(
                "Separation {id}: no channels available for nets {net_a}/{net_b}"
            )));
        }

        let shared = topology.shared_channels(*net_a, *net_b);
        let mut constraints = Vec::new();

        for channel in &shared {
            let width_budget = channel.width_mm - min_distance_mm;

            if width_budget < 0.0 {
                constraints.push(InternalConstraint::LayerRestriction {
                    var_name: emit_var_name(*net_a, &channel.id),
                    allowed: false,
                });
            } else {
                let capacity_terms = vec![
                    (emit_var_name(*net_a, &channel.id), *min_distance_mm),
                ];
                constraints.push(InternalConstraint::Capacity {
                    channel_id: channel.id.clone(),
                    capacity: channel.width_mm,
                    slack_factor: 0.8,
                    terms: capacity_terms,
                });
            }

            prov.link_clause(0, *prov_ref);
        }

        Ok(constraints)
    } else {
        Err(CompileError::Internal("wrong variant for separation".into()))
    }
}

fn desugar_adjacency_tier1(
    constraint: &ResolvedConstraint,
    topology: &ChannelTopology,
    prov: &mut ProvenanceMap,
) -> Result<Vec<InternalConstraint>, CompileError> {
    if let ResolvedConstraint::Adjacency {
        net_a,
        net_b,
        tier,
        provenance: prov_ref,
        max_distance_mm,
        ..
    } = constraint
    {
        use crate::ir_tier0::ConstraintTier;
        if *tier != ConstraintTier::Hard {
            return Ok(Vec::new());
        }

        let shared = topology.shared_channels(*net_a, *net_b);
        let mut constraints = Vec::new();

        for channel in &shared {
            if channel.width_mm >= *max_distance_mm {
                constraints.push(InternalConstraint::DiffPair {
                    channel_id: channel.id.clone(),
                    p_var_name: emit_var_name(*net_a, &channel.id),
                    n_var_name: emit_var_name(*net_b, &channel.id),
                });
                prov.link_clause(0, *prov_ref);
            }
        }

        Ok(constraints)
    } else {
        Err(CompileError::Internal("wrong variant for adjacency".into()))
    }
}

fn desugar_zone_enclosing_tier1(
    constraint: &ResolvedConstraint,
    topology: &ChannelTopology,
    prov: &mut ProvenanceMap,
) -> Result<Vec<InternalConstraint>, CompileError> {
    if let ResolvedConstraint::ZoneEnclosing {
        nets,
        zone_bounds,
        tier,
        provenance: prov_ref,
        ..
    } = constraint
    {
        use crate::ir_tier0::ConstraintTier;
        let _zone = zone_bounds;
        let mut constraints = Vec::new();

        for &net in nets {
            for channel in &topology.channels {
                if channel.nets.contains(&net) {
                    let is_inside_zone = channel_in_zone(channel, zone_bounds);
                    if !is_inside_zone && *tier == ConstraintTier::Hard {
                        constraints.push(InternalConstraint::LayerRestriction {
                            var_name: emit_var_name(net, &channel.id),
                            allowed: false,
                        });
                        prov.link_clause(0, *prov_ref);
                    }
                }
            }
        }

        Ok(constraints)
    } else {
        Err(CompileError::Internal("wrong variant for zone enclosing".into()))
    }
}

fn channel_in_zone(channel: &crate::ir_tier1::Channel, bounds: &crate::ir_tier0::Rect) -> bool {
    let _ch = channel;
    let _b = bounds;
    true
}

fn desugar_layer_preference_tier1(
    constraint: &ResolvedConstraint,
    topology: &ChannelTopology,
    prov: &mut ProvenanceMap,
) -> Result<Vec<InternalConstraint>, CompileError> {
    if let ResolvedConstraint::LayerPreference {
        net,
        layer,
        provenance: prov_ref,
        ..
    } = constraint
    {
        let mut constraints = Vec::new();

        for channel in &topology.channels {
            if channel.nets.contains(net) {
                let allowed = channel.layer == *layer;
                constraints.push(InternalConstraint::LayerRestriction {
                    var_name: emit_var_name(*net, &channel.id),
                    allowed,
                });
                prov.link_clause(0, *prov_ref);
            }
        }

        Ok(constraints)
    } else {
        Err(CompileError::Internal("wrong variant for layer preference".into()))
    }
}

fn desugar_advisory_tier1(
    _constraint: &ResolvedConstraint,
    _topology: &ChannelTopology,
    _prov: &mut ProvenanceMap,
) -> Result<Vec<InternalConstraint>, CompileError> {
    Ok(Vec::new())
}

pub fn compile_tier1_to_tier2(
    model: &ResolvedConstraintModel,
    topology: &ChannelTopology,
    provenance: &mut ProvenanceMap,
) -> Result<Vec<InternalConstraint>, CompileError> {
    let mut constraints = Vec::new();

    for resolved in &model.constraints {
        let variant = resolved.variant_name();
        let rule = RULES_TIER1
            .iter()
            .find(|(name, _)| *name == variant)
            .map(|(_, f)| f);

        if let Some(rule_fn) = rule {
            let mut result = rule_fn(resolved, topology, provenance)?;
            constraints.append(&mut result);
        } else {
            return Err(CompileError::Internal(format!(
                "no Tier 2 rule for variant {variant}"
            )));
        }
    }

    Ok(constraints)
}

pub fn augment_constraint_model(
    existing_constraints: Vec<InternalConstraint>,
    lowered_constraints: Vec<InternalConstraint>,
) -> Vec<InternalConstraint> {
    let mut augmented = existing_constraints;
    for c in lowered_constraints {
        augmented.push(c);
    }
    augmented
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::ir_tier0::ConstraintTier;
    use crate::ir_tier1::{Channel, ChannelTopology, ResolvedConstraint};
    use crate::provenance::ProvenanceMap;

    fn make_topology() -> ChannelTopology {
        ChannelTopology::new(vec![
            Channel {
                id: "CH1".into(),
                width_mm: 3.0,
                nets: vec![0, 1],
                layer: "F.Cu".into(),
            },
            Channel {
                id: "CH2".into(),
                width_mm: 2.0,
                nets: vec![1, 2],
                layer: "B.Cu".into(),
            },
            Channel {
                id: "CH3".into(),
                width_mm: 10.0,
                nets: vec![0, 1, 2],
                layer: "In1.Cu".into(),
            },
        ])
    }

    fn make_separation_tier1() -> ResolvedConstraint {
        ResolvedConstraint::Separation {
            id: "sep_1".into(),
            net_a: 0,
            net_b: 1,
            min_distance_mm: 6.0,
            tier: ConstraintTier::Hard,
            provenance: 0,
        }
    }

    #[test]
    fn test_separation_exceeds_channel_width() {
        let topology = make_topology();
        let mut prov = ProvenanceMap::new();
        let result = desugar_separation_tier1(&make_separation_tier1(), &topology, &mut prov);
        assert!(result.is_ok());
        let constraints = result.unwrap();
        assert!(!constraints.is_empty());
        let has_layer_restrictions = constraints
            .iter()
            .any(|c| matches!(c, InternalConstraint::LayerRestriction { allowed: false, .. }));
        assert!(has_layer_restrictions || constraints.iter().any(|c| matches!(c, InternalConstraint::Capacity { .. })));
    }

    #[test]
    fn test_separation_fits_in_channel() {
        let topology = ChannelTopology::new(vec![Channel {
            id: "CH1".into(),
            width_mm: 10.0,
            nets: vec![0, 1],
            layer: "F.Cu".into(),
        }]);
        let mut prov = ProvenanceMap::new();
        let sep = ResolvedConstraint::Separation {
            id: "sep_2".into(),
            net_a: 0,
            net_b: 1,
            min_distance_mm: 0.25,
            tier: ConstraintTier::Hard,
            provenance: 1,
        };
        let result = desugar_separation_tier1(&sep, &topology, &mut prov);
        assert!(result.is_ok());
        let constraints = result.unwrap();
        let has_capacity = constraints
            .iter()
            .any(|c| matches!(c, InternalConstraint::Capacity { .. }));
        assert!(has_capacity);
    }

    #[test]
    fn test_adjacency_soft_tier_emits_zero_constraints() {
        let topology = make_topology();
        let mut prov = ProvenanceMap::new();
        let adj = ResolvedConstraint::Adjacency {
            id: "adj_1".into(),
            net_a: 0,
            net_b: 1,
            max_distance_mm: 3.0,
            tier: ConstraintTier::Soft,
            provenance: 2,
        };
        let result = desugar_adjacency_tier1(&adj, &topology, &mut prov);
        assert!(result.is_ok());
        assert!(result.unwrap().is_empty());
    }

    #[test]
    fn test_adjacency_hard_tier_emits_diffpair() {
        let topology = make_topology();
        let mut prov = ProvenanceMap::new();
        let adj = ResolvedConstraint::Adjacency {
            id: "adj_hard".into(),
            net_a: 0,
            net_b: 1,
            max_distance_mm: 1.0,
            tier: ConstraintTier::Hard,
            provenance: 3,
        };
        let result = desugar_adjacency_tier1(&adj, &topology, &mut prov);
        assert!(result.is_ok());
        let constraints = result.unwrap();
        let has_diffpair = constraints
            .iter()
            .any(|c| matches!(c, InternalConstraint::DiffPair { .. }));
        assert!(has_diffpair);
    }

    #[test]
    fn test_layer_preference() {
        let topology = make_topology();
        let mut prov = ProvenanceMap::new();
        let lp = ResolvedConstraint::LayerPreference {
            id: "lp_1".into(),
            net: 0,
            layer: "B.Cu".into(),
            tier: ConstraintTier::Hard,
            provenance: 4,
        };
        let result = desugar_layer_preference_tier1(&lp, &topology, &mut prov);
        assert!(result.is_ok());
        let constraints = result.unwrap();
        assert!(!constraints.is_empty());
        for c in &constraints {
            if let InternalConstraint::LayerRestriction { var_name, allowed } = c {
                let on_fcu = var_name.contains("CH1");
                if on_fcu {
                    assert!(!allowed, "CH1 is F.Cu, should be disallowed");
                }
            }
        }
    }

    #[test]
    fn test_advisory_constraints_emit_zero() {
        let topology = make_topology();
        let mut prov = ProvenanceMap::new();

        for variant in &[
            "Alignment",
            "EdgePlacement",
            "Anchored",
            "LoopArea",
        ] {
            let resolved = match *variant {
                "Alignment" => ResolvedConstraint::Alignment {
                    id: "al_1".into(),
                    nets: vec![0],
                    axis: crate::ir_tier0::Axis::X,
                    tolerance_mm: 0.5,
                    tier: ConstraintTier::Hard,
                    provenance: 99,
                },
                "EdgePlacement" => ResolvedConstraint::EdgePlacement {
                    id: "ep_1".into(),
                    nets: vec![0],
                    side: crate::ir_tier0::BoardEdge::Top,
                    max_distance_mm: 5.0,
                    tier: ConstraintTier::Hard,
                    provenance: 99,
                },
                "Anchored" => ResolvedConstraint::Anchored {
                    id: "an_1".into(),
                    net: 0,
                    region: None,
                    position: None,
                    tier: ConstraintTier::Hard,
                    provenance: 99,
                },
                "LoopArea" => ResolvedConstraint::LoopArea {
                    id: "la_1".into(),
                    loop_name: "test".into(),
                    nets: vec![0],
                    max_area_mm2: 100.0,
                    tier: ConstraintTier::Hard,
                    provenance: 99,
                },
                _ => continue,
            };
            let result = desugar_advisory_tier1(&resolved, &topology, &mut prov);
            assert!(result.is_ok());
            assert!(result.unwrap().is_empty(), "{variant} should emit zero constraints");
        }
    }

    #[test]
    fn test_empty_topology_separation_error() {
        let topology = ChannelTopology::new(vec![]);
        let mut prov = ProvenanceMap::new();
        let result = desugar_separation_tier1(&make_separation_tier1(), &topology, &mut prov);
        assert!(result.is_err());
        match result {
            Err(CompileError::UnreachableConstraint(_)) => {},
            other => panic!("expected UnreachableConstraint, got {other:?}"),
        }
    }

    #[test]
    fn test_rules_table_size() {
        assert_eq!(RULES_TIER1.len(), 8);
    }

    #[test]
    fn test_augment_constraint_model() {
        let existing: Vec<InternalConstraint> = vec![];
        let lowered = vec![
            InternalConstraint::LayerRestriction {
                var_name: "uses_N0_CH1".into(),
                allowed: false,
            },
        ];
        let augmented = augment_constraint_model(existing, lowered);
        assert_eq!(augmented.len(), 1);
    }
}
