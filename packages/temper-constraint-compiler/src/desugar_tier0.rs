use crate::ir_tier0::{ConstraintTier, PclConstraint, PclConstraintModel};
use crate::ir_tier1::{
    ComponentResolver, ResolvedConstraint, ResolvedConstraintModel, ZoneResolver,
};
use crate::provenance::ProvenanceMap;
use crate::type_lattice::InferredNetPairConstraint;
use std::collections::HashMap;
use std::fmt;

#[derive(Debug, Clone)]
pub enum CompileError {
    UnresolvedComponent(String),
    UnresolvedZone(String),
    UnresolvedPin(String, String),
    UnreachableConstraint(String),
    Internal(String),
}

impl fmt::Display for CompileError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            CompileError::UnresolvedComponent(name) => {
                write!(f, "Unresolved component reference: {name}")
            }
            CompileError::UnresolvedZone(name) => {
                write!(f, "Unresolved zone reference: {name}")
            }
            CompileError::UnresolvedPin(component, pin) => {
                write!(f, "Unresolved pin {pin} on component {component}")
            }
            CompileError::UnreachableConstraint(msg) => {
                write!(f, "Unreachable constraint: {msg}")
            }
            CompileError::Internal(msg) => {
                write!(f, "Internal compile error: {msg}")
            }
        }
    }
}

pub type DesugarRuleTier0 = fn(
    constraint: &PclConstraint,
    component_resolver: &dyn ComponentResolver,
    zone_resolver: &dyn ZoneResolver,
    provenance: &mut ProvenanceMap,
) -> Result<Vec<ResolvedConstraint>, CompileError>;

pub static RULES_TIER0: &[(&str, DesugarRuleTier0)] = &[
    ("Adjacent", desugar_adjacent),
    ("Separated", desugar_separated),
    ("Enclosing", desugar_enclosing),
    ("Aligned", desugar_aligned),
    ("OnSide", desugar_on_side),
    ("Anchored", desugar_anchored),
    ("LoopArea", desugar_loop_area),
    ("InferredSeparation", desugar_inferred_separation),
];

fn resolve_components(
    names: &[String],
    resolver: &dyn ComponentResolver,
) -> Result<Vec<usize>, CompileError> {
    let mut indices = Vec::with_capacity(names.len());
    for name in names {
        match resolver.resolve(name) {
            Some(idx) => indices.push(idx),
            None => return Err(CompileError::UnresolvedComponent(name.clone())),
        }
    }
    Ok(indices)
}

fn desugar_adjacent(
    constraint: &PclConstraint,
    resolver: &dyn ComponentResolver,
    _zone_resolver: &dyn ZoneResolver,
    prov: &mut ProvenanceMap,
) -> Result<Vec<ResolvedConstraint>, CompileError> {
    if let PclConstraint::Adjacent {
        id,
        a,
        b,
        max_distance_mm,
        tier,
        because,
        ..
    } = constraint
    {
        let net_a = resolver
            .resolve(a)
            .ok_or_else(|| CompileError::UnresolvedComponent(a.clone()))?;
        let net_b = resolver
            .resolve(b)
            .ok_or_else(|| CompileError::UnresolvedComponent(b.clone()))?;
        let prov_ref = prov.push_tier0_and_return(
            id.clone(),
            "Adjacent".into(),
            "desugar_adjacent".into(),
            because.clone(),
            *tier,
        );
        Ok(vec![ResolvedConstraint::Adjacency {
            id: id.clone(),
            net_a,
            net_b,
            max_distance_mm: *max_distance_mm,
            tier: *tier,
            provenance: prov_ref,
        }])
    } else {
        Err(CompileError::Internal("wrong variant".into()))
    }
}

fn desugar_separated(
    constraint: &PclConstraint,
    resolver: &dyn ComponentResolver,
    _zone_resolver: &dyn ZoneResolver,
    prov: &mut ProvenanceMap,
) -> Result<Vec<ResolvedConstraint>, CompileError> {
    if let PclConstraint::Separated {
        id,
        a,
        b,
        min_distance_mm,
        tier,
        because,
        ..
    } = constraint
    {
        let net_a = resolver
            .resolve(a)
            .ok_or_else(|| CompileError::UnresolvedComponent(a.clone()))?;
        let net_b = resolver
            .resolve(b)
            .ok_or_else(|| CompileError::UnresolvedComponent(b.clone()))?;
        let prov_ref = prov.push_tier0_and_return(
            id.clone(),
            "Separated".into(),
            "desugar_separated".into(),
            because.clone(),
            *tier,
        );
        Ok(vec![ResolvedConstraint::Separation {
            id: id.clone(),
            net_a,
            net_b,
            min_distance_mm: *min_distance_mm,
            tier: *tier,
            provenance: prov_ref,
        }])
    } else {
        Err(CompileError::Internal("wrong variant".into()))
    }
}

fn desugar_enclosing(
    constraint: &PclConstraint,
    resolver: &dyn ComponentResolver,
    zone_resolver: &dyn ZoneResolver,
    prov: &mut ProvenanceMap,
) -> Result<Vec<ResolvedConstraint>, CompileError> {
    if let PclConstraint::Enclosing {
        id,
        outer,
        inner,
        margin_mm,
        tier,
        because,
    } = constraint
    {
        let zone_bounds = zone_resolver
            .resolve(outer)
            .ok_or_else(|| CompileError::UnresolvedZone(outer.clone()))?;
        let nets = resolve_components(inner, resolver)?;
        let prov_ref = prov.push_tier0_and_return(
            id.clone(),
            "Enclosing".into(),
            "desugar_enclosing".into(),
            because.clone(),
            *tier,
        );
        Ok(vec![ResolvedConstraint::ZoneEnclosing {
            id: id.clone(),
            nets,
            zone_bounds,
            margin_mm: *margin_mm,
            tier: *tier,
            provenance: prov_ref,
        }])
    } else {
        Err(CompileError::Internal("wrong variant".into()))
    }
}

fn desugar_aligned(
    constraint: &PclConstraint,
    resolver: &dyn ComponentResolver,
    _zone_resolver: &dyn ZoneResolver,
    prov: &mut ProvenanceMap,
) -> Result<Vec<ResolvedConstraint>, CompileError> {
    if let PclConstraint::Aligned {
        id,
        components,
        axis,
        tolerance_mm,
        tier,
        because,
    } = constraint
    {
        let nets = resolve_components(components, resolver)?;
        let axis = axis.unwrap_or(crate::ir_tier0::Axis::X);
        let prov_ref = prov.push_tier0_and_return(
            id.clone(),
            "Aligned".into(),
            "desugar_aligned".into(),
            because.clone(),
            *tier,
        );
        Ok(vec![ResolvedConstraint::Alignment {
            id: id.clone(),
            nets,
            axis,
            tolerance_mm: *tolerance_mm,
            tier: *tier,
            provenance: prov_ref,
        }])
    } else {
        Err(CompileError::Internal("wrong variant".into()))
    }
}

fn desugar_on_side(
    constraint: &PclConstraint,
    resolver: &dyn ComponentResolver,
    _zone_resolver: &dyn ZoneResolver,
    prov: &mut ProvenanceMap,
) -> Result<Vec<ResolvedConstraint>, CompileError> {
    if let PclConstraint::OnSide {
        id,
        components,
        side,
        max_distance_mm,
        tier,
        because,
        ..
    } = constraint
    {
        let nets = resolve_components(components, resolver)?;
        let side = side.unwrap_or(crate::ir_tier0::BoardEdge::Top);
        let prov_ref = prov.push_tier0_and_return(
            id.clone(),
            "OnSide".into(),
            "desugar_on_side".into(),
            because.clone(),
            *tier,
        );
        Ok(vec![ResolvedConstraint::EdgePlacement {
            id: id.clone(),
            nets,
            side,
            max_distance_mm: *max_distance_mm,
            tier: *tier,
            provenance: prov_ref,
        }])
    } else {
        Err(CompileError::Internal("wrong variant".into()))
    }
}

fn desugar_anchored(
    constraint: &PclConstraint,
    resolver: &dyn ComponentResolver,
    _zone_resolver: &dyn ZoneResolver,
    prov: &mut ProvenanceMap,
) -> Result<Vec<ResolvedConstraint>, CompileError> {
    if let PclConstraint::Anchored {
        id,
        component,
        region,
        position,
        tier,
        because,
    } = constraint
    {
        let net = resolver
            .resolve(component)
            .ok_or_else(|| CompileError::UnresolvedComponent(component.clone()))?;
        let prov_ref = prov.push_tier0_and_return(
            id.clone(),
            "Anchored".into(),
            "desugar_anchored".into(),
            because.clone(),
            *tier,
        );
        Ok(vec![ResolvedConstraint::Anchored {
            id: id.clone(),
            net,
            region: *region,
            position: *position,
            tier: *tier,
            provenance: prov_ref,
        }])
    } else {
        Err(CompileError::Internal("wrong variant".into()))
    }
}

fn desugar_loop_area(
    constraint: &PclConstraint,
    resolver: &dyn ComponentResolver,
    _zone_resolver: &dyn ZoneResolver,
    prov: &mut ProvenanceMap,
) -> Result<Vec<ResolvedConstraint>, CompileError> {
    if let PclConstraint::LoopArea {
        id,
        loop_name,
        max_area_mm2,
        tier,
        because,
        components,
    } = constraint
    {
        let nets = resolve_components(components, resolver)?;
        let prov_ref = prov.push_tier0_and_return(
            id.clone(),
            "LoopArea".into(),
            "desugar_loop_area".into(),
            because.clone(),
            *tier,
        );
        Ok(vec![ResolvedConstraint::LoopArea {
            id: id.clone(),
            loop_name: loop_name.clone(),
            nets,
            max_area_mm2: *max_area_mm2,
            tier: *tier,
            provenance: prov_ref,
        }])
    } else {
        Err(CompileError::Internal("wrong variant".into()))
    }
}

fn desugar_inferred_separation(
    constraint: &PclConstraint,
    resolver: &dyn ComponentResolver,
    _zone_resolver: &dyn ZoneResolver,
    prov: &mut ProvenanceMap,
) -> Result<Vec<ResolvedConstraint>, CompileError> {
    if let PclConstraint::InferredSeparation {
        id,
        source_pair,
        clearance_floor_mm,
        layer_restriction,
        tier,
        because,
    } = constraint
    {
        let net_a = resolver
            .resolve(&source_pair.0)
            .ok_or_else(|| CompileError::UnresolvedComponent(source_pair.0.clone()))?;
        let net_b = resolver
            .resolve(&source_pair.1)
            .ok_or_else(|| CompileError::UnresolvedComponent(source_pair.1.clone()))?;
        let prov_ref = prov.push_tier0_and_return(
            id.clone(),
            "InferredSeparation".into(),
            "desugar_inferred_separation".into(),
            because.clone(),
            *tier,
        );
        let mut results = vec![ResolvedConstraint::Separation {
            id: id.clone(),
            net_a,
            net_b,
            min_distance_mm: *clearance_floor_mm,
            tier: *tier,
            provenance: prov_ref,
        }];
        if let Some(layer) = layer_restriction {
            let layer_prov_ref = prov.push_tier0_and_return(
                format!("{id}_layer"),
                "InferredSeparation".into(),
                "desugar_inferred_separation".into(),
                because.clone(),
                *tier,
            );
            results.push(ResolvedConstraint::LayerPreference {
                id: format!("{id}_layer"),
                net: net_a,
                layer: layer.clone(),
                tier: *tier,
                provenance: layer_prov_ref,
            });
        }
        Ok(results)
    } else {
        Err(CompileError::Internal("wrong variant".into()))
    }
}

pub fn compile_tier0_to_tier1(
    model: &PclConstraintModel,
    component_resolver: &dyn ComponentResolver,
    zone_resolver: &dyn ZoneResolver,
    provenance: &mut ProvenanceMap,
) -> Result<ResolvedConstraintModel, CompileError> {
    let mut resolved = Vec::new();
    let net_class_map = HashMap::new();

    for constraint in model.all_constraints() {
        let variant = constraint.variant_name();
        let rule = RULES_TIER0
            .iter()
            .find(|(name, _)| *name == variant)
            .map(|(_, f)| f);

        if let Some(rule_fn) = rule {
            let mut result = rule_fn(constraint, component_resolver, zone_resolver, provenance)?;
            resolved.append(&mut result);
        } else {
            return Err(CompileError::Internal(format!(
                "no desugaring rule for variant {variant}"
            )));
        }
    }

    Ok(ResolvedConstraintModel::new(resolved, net_class_map))
}

pub fn compile_lattice_inferred_to_tier0(
    inferred: &[InferredNetPairConstraint],
    lattice: &crate::type_lattice::TypeLattice,
) -> Vec<PclConstraint> {
    inferred
        .iter()
        .map(|ipc| {
            let id = format!(
                "lattice_infer_{}_{}_{}",
                ipc.net_a,
                ipc.net_b,
                ipc.channel_id.as_deref().unwrap_or("?")
            );
            PclConstraint::InferredSeparation {
                id,
                source_pair: (ipc.net_class_a.clone(), ipc.net_class_b.clone()),
                clearance_floor_mm: ipc.clearance_floor_mm,
                layer_restriction: ipc.layer_restriction.clone(),
                tier: ConstraintTier::Hard,
                because: format!(
                    "Type lattice inferred separation between {}/{} (join = {:?})",
                    ipc.net_class_a,
                    ipc.net_class_b,
                    lattice.join(
                        crate::type_lattice::SafetyCategory::from_str(&ipc.net_class_a)
                            .unwrap_or(crate::type_lattice::SafetyCategory::LV),
                        crate::type_lattice::SafetyCategory::from_str(&ipc.net_class_b)
                            .unwrap_or(crate::type_lattice::SafetyCategory::LV),
                    )
                ),
            }
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::ir_tier0::{PclConstraint, PclConstraintModel};
    use crate::ir_tier0::Rect;
    use std::collections::HashMap;

    struct StubResolver {
        map: HashMap<String, usize>,
    }

    impl StubResolver {
        fn new(map: HashMap<String, usize>) -> Self {
            Self { map }
        }
    }

    impl ComponentResolver for StubResolver {
        fn resolve(&self, component_ref: &str) -> Option<usize> {
            self.map.get(component_ref).copied()
        }
    }

    impl ZoneResolver for StubResolver {
        fn resolve(&self, _zone_name: &str) -> Option<Rect> {
            Some(Rect {
                x_min: 0.0,
                y_min: 0.0,
                x_max: 100.0,
                y_max: 100.0,
            })
        }
    }

    fn make_adjacent_pcl() -> PclConstraint {
        PclConstraint::Adjacent {
            id: "adj_1".into(),
            a: "Q1".into(),
            b: "Q2".into(),
            max_distance_mm: 10.0,
            tier: ConstraintTier::Hard,
            because: "half-bridge".into(),
            metric: None,
            pin_a: None,
            pin_b: None,
        }
    }

    fn make_separated_pcl() -> PclConstraint {
        PclConstraint::Separated {
            id: "sep_1".into(),
            a: "HV1".into(),
            b: "LV1".into(),
            min_distance_mm: 6.0,
            tier: ConstraintTier::Hard,
            because: "HV isolation".into(),
            metric: None,
        }
    }

    fn make_inferred_pcl() -> PclConstraint {
        PclConstraint::InferredSeparation {
            id: "inf_1".into(),
            source_pair: ("HighVoltage".into(), "Signal".into()),
            clearance_floor_mm: 6.0,
            layer_restriction: Some("B.Cu".into()),
            tier: ConstraintTier::Hard,
            because: "HV-LV isolation inferred".into(),
        }
    }

    #[test]
    fn test_desugar_adjacent() {
        let mut resolver_map = HashMap::new();
        resolver_map.insert("Q1".to_string(), 0);
        resolver_map.insert("Q2".to_string(), 1);
        let resolver = StubResolver::new(resolver_map);
        let mut prov = ProvenanceMap::new();

        let result = desugar_adjacent(&make_adjacent_pcl(), &resolver, &resolver, &mut prov);
        assert!(result.is_ok());
        let constraints = result.unwrap();
        assert_eq!(constraints.len(), 1);
        if let ResolvedConstraint::Adjacency { net_a, net_b, .. } = &constraints[0] {
            assert_eq!(*net_a, 0);
            assert_eq!(*net_b, 1);
        } else {
            panic!("expected Adjacency");
        }
        assert_eq!(prov.entries.len(), 1);
    }

    #[test]
    fn test_desugar_separated() {
        let mut resolver_map = HashMap::new();
        resolver_map.insert("HV1".to_string(), 3);
        resolver_map.insert("LV1".to_string(), 7);
        let resolver = StubResolver::new(resolver_map);
        let mut prov = ProvenanceMap::new();

        let result = desugar_separated(&make_separated_pcl(), &resolver, &resolver, &mut prov);
        assert!(result.is_ok());
        let constraints = result.unwrap();
        if let ResolvedConstraint::Separation { net_a, net_b, min_distance_mm, .. } = &constraints[0] {
            assert_eq!(*net_a, 3);
            assert_eq!(*net_b, 7);
            assert_eq!(*min_distance_mm, 6.0);
        } else {
            panic!("expected Separation");
        }
    }

    #[test]
    fn test_desugar_inferred_separation() {
        let mut resolver_map = HashMap::new();
        resolver_map.insert("HighVoltage".to_string(), 0);
        resolver_map.insert("Signal".to_string(), 5);
        let resolver = StubResolver::new(resolver_map);
        let mut prov = ProvenanceMap::new();

        let result = desugar_inferred_separation(&make_inferred_pcl(), &resolver, &resolver, &mut prov);
        assert!(result.is_ok());
        let constraints = result.unwrap();
        assert_eq!(constraints.len(), 2);
    }

    #[test]
    fn test_unresolved_component_error() {
        let resolver = StubResolver::new(HashMap::new());
        let mut prov = ProvenanceMap::new();
        let result = desugar_adjacent(&make_adjacent_pcl(), &resolver, &resolver, &mut prov);
        assert!(result.is_err());
        match result {
            Err(CompileError::UnresolvedComponent(name)) => assert_eq!(name, "Q1"),
            other => panic!("expected UnresolvedComponent, got {other:?}"),
        }
    }

    #[test]
    fn test_compile_empty_model() {
        let model = PclConstraintModel::new(vec![], vec![]);
        let resolver = StubResolver::new(HashMap::new());
        let mut prov = ProvenanceMap::new();
        let result = compile_tier0_to_tier1(&model, &resolver, &resolver, &mut prov);
        assert!(result.is_ok());
        let resolved_model = result.unwrap();
        assert!(resolved_model.is_empty());
    }

    #[test]
    fn test_rules_table_size() {
        assert_eq!(RULES_TIER0.len(), 8);
    }

    #[test]
    fn test_provenance_references_are_valid() {
        let mut resolver_map = HashMap::new();
        resolver_map.insert("Q1".to_string(), 0);
        resolver_map.insert("Q2".to_string(), 1);
        let resolver = StubResolver::new(resolver_map);
        let mut prov = ProvenanceMap::new();

        let result = desugar_adjacent(&make_adjacent_pcl(), &resolver, &resolver, &mut prov).unwrap();
        let prov_ref = result[0].provenance();
        assert!(prov.get(prov_ref).is_some());
    }
}
