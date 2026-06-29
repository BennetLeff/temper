use crate::ir_tier0::{Axis, BoardEdge, ConstraintTier, Point};
pub use crate::ir_tier0::Rect;
use crate::type_lattice::NetClassMetadata;
use std::collections::HashMap;
use std::fmt;

pub type ProvenanceRef = usize;

#[derive(Debug, Clone)]
pub enum ResolvedConstraint {
    Separation {
        id: String,
        net_a: usize,
        net_b: usize,
        min_distance_mm: f64,
        tier: ConstraintTier,
        provenance: ProvenanceRef,
    },
    Adjacency {
        id: String,
        net_a: usize,
        net_b: usize,
        max_distance_mm: f64,
        tier: ConstraintTier,
        provenance: ProvenanceRef,
    },
    ZoneEnclosing {
        id: String,
        nets: Vec<usize>,
        zone_bounds: Rect,
        margin_mm: f64,
        tier: ConstraintTier,
        provenance: ProvenanceRef,
    },
    LayerPreference {
        id: String,
        net: usize,
        layer: String,
        tier: ConstraintTier,
        provenance: ProvenanceRef,
    },
    Alignment {
        id: String,
        nets: Vec<usize>,
        axis: Axis,
        tolerance_mm: f64,
        tier: ConstraintTier,
        provenance: ProvenanceRef,
    },
    EdgePlacement {
        id: String,
        nets: Vec<usize>,
        side: BoardEdge,
        max_distance_mm: f64,
        tier: ConstraintTier,
        provenance: ProvenanceRef,
    },
    Anchored {
        id: String,
        net: usize,
        region: Option<Rect>,
        position: Option<Point>,
        tier: ConstraintTier,
        provenance: ProvenanceRef,
    },
    LoopArea {
        id: String,
        loop_name: String,
        nets: Vec<usize>,
        max_area_mm2: f64,
        tier: ConstraintTier,
        provenance: ProvenanceRef,
    },
}

impl ResolvedConstraint {
    pub fn id(&self) -> &str {
        match self {
            ResolvedConstraint::Separation { id, .. } => id,
            ResolvedConstraint::Adjacency { id, .. } => id,
            ResolvedConstraint::ZoneEnclosing { id, .. } => id,
            ResolvedConstraint::LayerPreference { id, .. } => id,
            ResolvedConstraint::Alignment { id, .. } => id,
            ResolvedConstraint::EdgePlacement { id, .. } => id,
            ResolvedConstraint::Anchored { id, .. } => id,
            ResolvedConstraint::LoopArea { id, .. } => id,
        }
    }

    pub fn variant_name(&self) -> &'static str {
        match self {
            ResolvedConstraint::Separation { .. } => "Separation",
            ResolvedConstraint::Adjacency { .. } => "Adjacency",
            ResolvedConstraint::ZoneEnclosing { .. } => "ZoneEnclosing",
            ResolvedConstraint::LayerPreference { .. } => "LayerPreference",
            ResolvedConstraint::Alignment { .. } => "Alignment",
            ResolvedConstraint::EdgePlacement { .. } => "EdgePlacement",
            ResolvedConstraint::Anchored { .. } => "Anchored",
            ResolvedConstraint::LoopArea { .. } => "LoopArea",
        }
    }

    pub fn tier(&self) -> ConstraintTier {
        match self {
            ResolvedConstraint::Separation { tier, .. } => *tier,
            ResolvedConstraint::Adjacency { tier, .. } => *tier,
            ResolvedConstraint::ZoneEnclosing { tier, .. } => *tier,
            ResolvedConstraint::LayerPreference { tier, .. } => *tier,
            ResolvedConstraint::Alignment { tier, .. } => *tier,
            ResolvedConstraint::EdgePlacement { tier, .. } => *tier,
            ResolvedConstraint::Anchored { tier, .. } => *tier,
            ResolvedConstraint::LoopArea { tier, .. } => *tier,
        }
    }

    pub fn provenance(&self) -> ProvenanceRef {
        match self {
            ResolvedConstraint::Separation { provenance, .. } => *provenance,
            ResolvedConstraint::Adjacency { provenance, .. } => *provenance,
            ResolvedConstraint::ZoneEnclosing { provenance, .. } => *provenance,
            ResolvedConstraint::LayerPreference { provenance, .. } => *provenance,
            ResolvedConstraint::Alignment { provenance, .. } => *provenance,
            ResolvedConstraint::EdgePlacement { provenance, .. } => *provenance,
            ResolvedConstraint::Anchored { provenance, .. } => *provenance,
            ResolvedConstraint::LoopArea { provenance, .. } => *provenance,
        }
    }
}

impl fmt::Display for ResolvedConstraint {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            ResolvedConstraint::Separation {
                id,
                net_a,
                net_b,
                min_distance_mm,
                tier,
                ..
            } => {
                write!(f, "Separation({id}): net{net_a} ‖ net{net_b} ≥ {min_distance_mm}mm [{tier}]")
            }
            ResolvedConstraint::Adjacency {
                id,
                net_a,
                net_b,
                max_distance_mm,
                tier,
                ..
            } => {
                write!(f, "Adjacency({id}): net{net_a} ↔ net{net_b} ≤ {max_distance_mm}mm [{tier}]")
            }
            ResolvedConstraint::ZoneEnclosing {
                id, nets, tier, ..
            } => {
                write!(f, "ZoneEnclosing({id}): {:?} [{tier}]", nets)
            }
            ResolvedConstraint::LayerPreference {
                id, net, layer, tier, ..
            } => {
                write!(f, "LayerPreference({id}): net{net} on {layer} [{tier}]")
            }
            ResolvedConstraint::Alignment {
                id, nets, axis, tier, ..
            } => {
                write!(f, "Alignment({id}): {:?} on {axis:?} [{tier}]", nets)
            }
            ResolvedConstraint::EdgePlacement {
                id, nets, side, tier, ..
            } => {
                write!(f, "EdgePlacement({id}): {:?} at {side:?} [{tier}]", nets)
            }
            ResolvedConstraint::Anchored {
                id, net, tier, ..
            } => {
                write!(f, "Anchored({id}): net{net} [{tier}]")
            }
            ResolvedConstraint::LoopArea {
                id,
                loop_name,
                nets,
                max_area_mm2,
                tier,
                ..
            } => {
                write!(f, "LoopArea({id}): {loop_name} ({:?}) ≤ {max_area_mm2}mm² [{tier}]", nets)
            }
        }
    }
}

#[derive(Debug, Clone)]
pub struct ResolvedConstraintModel {
    pub constraints: Vec<ResolvedConstraint>,
    pub net_class_map: HashMap<usize, NetClassMetadata>,
}

impl ResolvedConstraintModel {
    pub fn new(
        constraints: Vec<ResolvedConstraint>,
        net_class_map: HashMap<usize, NetClassMetadata>,
    ) -> Self {
        Self {
            constraints,
            net_class_map,
        }
    }

    pub fn is_empty(&self) -> bool {
        self.constraints.is_empty()
    }
}

pub trait ComponentResolver {
    fn resolve(&self, component_ref: &str) -> Option<usize>;
}

pub trait ZoneResolver {
    fn resolve(&self, zone_name: &str) -> Option<Rect>;
}

#[derive(Debug, Clone)]
pub struct Channel {
    pub id: String,
    pub width_mm: f64,
    pub nets: Vec<usize>,
    pub layer: String,
}

#[derive(Debug, Clone)]
pub struct ChannelTopology {
    pub channels: Vec<Channel>,
}

impl ChannelTopology {
    pub fn new(channels: Vec<Channel>) -> Self {
        Self { channels }
    }

    pub fn shared_channels(&self, net_a: usize, net_b: usize) -> Vec<&Channel> {
        self.channels
            .iter()
            .filter(|c| c.nets.contains(&net_a) && c.nets.contains(&net_b))
            .collect()
    }

    pub fn channels_for_net(&self, net: usize) -> Vec<&Channel> {
        self.channels
            .iter()
            .filter(|c| c.nets.contains(&net))
            .collect()
    }

    pub fn is_empty(&self) -> bool {
        self.channels.is_empty()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn make_separation() -> ResolvedConstraint {
        ResolvedConstraint::Separation {
            id: "sep_1".into(),
            net_a: 0,
            net_b: 1,
            min_distance_mm: 6.0,
            tier: ConstraintTier::Hard,
            provenance: 0,
        }
    }

    fn make_adjacency() -> ResolvedConstraint {
        ResolvedConstraint::Adjacency {
            id: "adj_1".into(),
            net_a: 2,
            net_b: 3,
            max_distance_mm: 3.0,
            tier: ConstraintTier::Strong,
            provenance: 1,
        }
    }

    fn make_zone_enclosing() -> ResolvedConstraint {
        ResolvedConstraint::ZoneEnclosing {
            id: "enc_1".into(),
            nets: vec![0, 2],
            zone_bounds: Rect {
                x_min: 0.0,
                y_min: 0.0,
                x_max: 100.0,
                y_max: 100.0,
            },
            margin_mm: 2.0,
            tier: ConstraintTier::Hard,
            provenance: 2,
        }
    }

    fn make_layer_preference() -> ResolvedConstraint {
        ResolvedConstraint::LayerPreference {
            id: "layer_1".into(),
            net: 5,
            layer: "B.Cu".into(),
            tier: ConstraintTier::Hard,
            provenance: 3,
        }
    }

    #[test]
    fn test_variant_names() {
        assert_eq!(make_separation().variant_name(), "Separation");
        assert_eq!(make_adjacency().variant_name(), "Adjacency");
        assert_eq!(make_zone_enclosing().variant_name(), "ZoneEnclosing");
        assert_eq!(make_layer_preference().variant_name(), "LayerPreference");
    }

    #[test]
    fn test_display() {
        let sep = make_separation();
        assert!(format!("{sep}").contains("net0 ‖ net1 ≥ 6mm"));
    }

    #[test]
    fn test_provenance_ref() {
        assert_eq!(make_separation().provenance(), 0);
        assert_eq!(make_adjacency().provenance(), 1);
    }

    #[test]
    fn test_channel_topology_shared_channels() {
        let topology = ChannelTopology::new(vec![
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
        ]);
        let shared = topology.shared_channels(0, 1);
        assert_eq!(shared.len(), 1);
        assert_eq!(shared[0].id, "CH1");
        let not_shared = topology.shared_channels(0, 2);
        assert_eq!(not_shared.len(), 0);
    }

    #[test]
    fn test_channel_topology_channels_for_net() {
        let topology = ChannelTopology::new(vec![
            Channel {
                id: "CH1".into(),
                width_mm: 3.0,
                nets: vec![0, 1],
                layer: "F.Cu".into(),
            },
            Channel {
                id: "CH2".into(),
                width_mm: 2.0,
                nets: vec![0, 2],
                layer: "B.Cu".into(),
            },
        ]);
        let channels = topology.channels_for_net(0);
        assert_eq!(channels.len(), 2);
        assert_eq!(topology.channels_for_net(3).len(), 0);
    }

    #[test]
    fn test_resolved_constraint_model_empty() {
        let model = ResolvedConstraintModel::new(vec![], HashMap::new());
        assert!(model.is_empty());
    }
}
