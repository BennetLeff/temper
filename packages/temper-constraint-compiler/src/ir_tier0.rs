use std::fmt;

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
pub enum ConstraintTier {
    Hard = 1,
    Strong = 2,
    Soft = 3,
}

impl ConstraintTier {
    pub fn from_str(s: &str) -> Option<Self> {
        match s.to_lowercase().as_str() {
            "hard" => Some(ConstraintTier::Hard),
            "strong" => Some(ConstraintTier::Strong),
            "soft" => Some(ConstraintTier::Soft),
            _ => None,
        }
    }
}

impl fmt::Display for ConstraintTier {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            ConstraintTier::Hard => write!(f, "HARD"),
            ConstraintTier::Strong => write!(f, "STRONG"),
            ConstraintTier::Soft => write!(f, "SOFT"),
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Axis {
    X,
    Y,
    Major,
    Minor,
}

impl Axis {
    pub fn from_str(s: &str) -> Option<Self> {
        match s.to_lowercase().as_str() {
            "x" => Some(Axis::X),
            "y" => Some(Axis::Y),
            "major" => Some(Axis::Major),
            "minor" => Some(Axis::Minor),
            _ => None,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum BoardEdge {
    Top,
    Bottom,
    Left,
    Right,
}

impl BoardEdge {
    pub fn from_str(s: &str) -> Option<Self> {
        match s.to_lowercase().as_str() {
            "top" => Some(BoardEdge::Top),
            "bottom" => Some(BoardEdge::Bottom),
            "left" => Some(BoardEdge::Left),
            "right" => Some(BoardEdge::Right),
            _ => None,
        }
    }
}

#[derive(Debug, Clone, Copy)]
pub struct Rect {
    pub x_min: f64,
    pub y_min: f64,
    pub x_max: f64,
    pub y_max: f64,
}

#[derive(Debug, Clone, Copy)]
pub struct Point {
    pub x: f64,
    pub y: f64,
}

pub type ConstraintId = String;

#[derive(Debug, Clone)]
pub enum PclConstraint {
    Adjacent {
        id: ConstraintId,
        a: String,
        b: String,
        max_distance_mm: f64,
        tier: ConstraintTier,
        because: String,
        metric: Option<String>,
        pin_a: Option<String>,
        pin_b: Option<String>,
    },
    Separated {
        id: ConstraintId,
        a: String,
        b: String,
        min_distance_mm: f64,
        tier: ConstraintTier,
        because: String,
        metric: Option<String>,
    },
    Enclosing {
        id: ConstraintId,
        outer: String,
        inner: Vec<String>,
        margin_mm: f64,
        tier: ConstraintTier,
        because: String,
    },
    Aligned {
        id: ConstraintId,
        components: Vec<String>,
        axis: Option<Axis>,
        tolerance_mm: f64,
        tier: ConstraintTier,
        because: String,
    },
    OnSide {
        id: ConstraintId,
        components: Vec<String>,
        side: Option<BoardEdge>,
        edge: Option<String>,
        max_distance_mm: f64,
        tier: ConstraintTier,
        because: String,
    },
    Anchored {
        id: ConstraintId,
        component: String,
        region: Option<Rect>,
        position: Option<Point>,
        tier: ConstraintTier,
        because: String,
    },
    LoopArea {
        id: ConstraintId,
        loop_name: String,
        max_area_mm2: f64,
        tier: ConstraintTier,
        because: String,
        components: Vec<String>,
    },
    InferredSeparation {
        id: ConstraintId,
        source_pair: (String, String),
        clearance_floor_mm: f64,
        layer_restriction: Option<String>,
        tier: ConstraintTier,
        because: String,
    },
}

impl PclConstraint {
    pub fn id(&self) -> &str {
        match self {
            PclConstraint::Adjacent { id, .. } => id,
            PclConstraint::Separated { id, .. } => id,
            PclConstraint::Enclosing { id, .. } => id,
            PclConstraint::Aligned { id, .. } => id,
            PclConstraint::OnSide { id, .. } => id,
            PclConstraint::Anchored { id, .. } => id,
            PclConstraint::LoopArea { id, .. } => id,
            PclConstraint::InferredSeparation { id, .. } => id,
        }
    }

    pub fn tier(&self) -> ConstraintTier {
        match self {
            PclConstraint::Adjacent { tier, .. } => *tier,
            PclConstraint::Separated { tier, .. } => *tier,
            PclConstraint::Enclosing { tier, .. } => *tier,
            PclConstraint::Aligned { tier, .. } => *tier,
            PclConstraint::OnSide { tier, .. } => *tier,
            PclConstraint::Anchored { tier, .. } => *tier,
            PclConstraint::LoopArea { tier, .. } => *tier,
            PclConstraint::InferredSeparation { tier, .. } => *tier,
        }
    }

    pub fn variant_name(&self) -> &'static str {
        match self {
            PclConstraint::Adjacent { .. } => "Adjacent",
            PclConstraint::Separated { .. } => "Separated",
            PclConstraint::Enclosing { .. } => "Enclosing",
            PclConstraint::Aligned { .. } => "Aligned",
            PclConstraint::OnSide { .. } => "OnSide",
            PclConstraint::Anchored { .. } => "Anchored",
            PclConstraint::LoopArea { .. } => "LoopArea",
            PclConstraint::InferredSeparation { .. } => "InferredSeparation",
        }
    }
}

impl fmt::Display for PclConstraint {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            PclConstraint::Adjacent { id, a, b, tier, because, .. } => {
                write!(f, "Adjacent({id}): {a} ↔ {b} [{tier}] — {because}")
            }
            PclConstraint::Separated { id, a, b, min_distance_mm, tier, because, .. } => {
                write!(f, "Separated({id}): {a} ‖ {b} ≥ {min_distance_mm}mm [{tier}] — {because}")
            }
            PclConstraint::Enclosing { id, outer, inner, margin_mm, tier, because, .. } => {
                write!(f, "Enclosing({id}): {outer} contains {:?} with margin {margin_mm}mm [{tier}] — {because}", inner)
            }
            PclConstraint::Aligned { id, components, axis, tier, because, .. } => {
                write!(f, "Aligned({id}): {:?} on {axis:?} [{tier}] — {because}", components)
            }
            PclConstraint::OnSide { id, components, side, tier, because, .. } => {
                write!(f, "OnSide({id}): {:?} at {side:?} [{tier}] — {because}", components)
            }
            PclConstraint::Anchored { id, component, tier, because, .. } => {
                write!(f, "Anchored({id}): {component} [{tier}] — {because}")
            }
            PclConstraint::LoopArea { id, loop_name, max_area_mm2, tier, because, .. } => {
                write!(f, "LoopArea({id}): {loop_name} ≤ {max_area_mm2}mm² [{tier}] — {because}")
            }
            PclConstraint::InferredSeparation { id, source_pair, clearance_floor_mm, tier, .. } => {
                write!(f, "InferredSeparation({id}): {}/{} ≥ {clearance_floor_mm}mm [{tier}]", source_pair.0, source_pair.1)
            }
        }
    }
}

#[derive(Debug, Clone)]
pub struct PclConstraintModel {
    pub pcl_constraints: Vec<PclConstraint>,
    pub inferred_constraints: Vec<PclConstraint>,
}

impl PclConstraintModel {
    pub fn new(
        pcl_constraints: Vec<PclConstraint>,
        inferred_constraints: Vec<PclConstraint>,
    ) -> Self {
        Self {
            pcl_constraints,
            inferred_constraints,
        }
    }

    pub fn all_constraints(&self) -> impl Iterator<Item = &PclConstraint> {
        self.pcl_constraints.iter().chain(self.inferred_constraints.iter())
    }

    pub fn is_empty(&self) -> bool {
        self.pcl_constraints.is_empty() && self.inferred_constraints.is_empty()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn make_adjacent() -> PclConstraint {
        PclConstraint::Adjacent {
            id: "adj_1".into(),
            a: "Q1".into(),
            b: "Q2".into(),
            max_distance_mm: 10.0,
            tier: ConstraintTier::Hard,
            because: "half-bridge commutation loop".into(),
            metric: Some("edge_to_edge".into()),
            pin_a: None,
            pin_b: None,
        }
    }

    fn make_separated() -> PclConstraint {
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

    fn make_enclosing() -> PclConstraint {
        PclConstraint::Enclosing {
            id: "enc_1".into(),
            outer: "HV_ZONE".into(),
            inner: vec!["Q1".into(), "D1".into()],
            margin_mm: 2.0,
            tier: ConstraintTier::Strong,
            because: "Keep HV components in HV zone".into(),
        }
    }

    fn make_aligned() -> PclConstraint {
        PclConstraint::Aligned {
            id: "aln_1".into(),
            components: vec!["Q1".into(), "Q2".into(), "D1".into()],
            axis: Some(Axis::X),
            tolerance_mm: 0.5,
            tier: ConstraintTier::Strong,
            because: "thermal coupling".into(),
        }
    }

    fn make_on_side() -> PclConstraint {
        PclConstraint::OnSide {
            id: "side_1".into(),
            components: vec!["CONN1".into()],
            side: Some(BoardEdge::Top),
            edge: None,
            max_distance_mm: 5.0,
            tier: ConstraintTier::Soft,
            because: "connector accessibility".into(),
        }
    }

    fn make_anchored() -> PclConstraint {
        PclConstraint::Anchored {
            id: "anc_1".into(),
            component: "MCU".into(),
            region: Some(Rect {
                x_min: 0.0,
                y_min: 0.0,
                x_max: 50.0,
                y_max: 50.0,
            }),
            position: None,
            tier: ConstraintTier::Hard,
            because: "MCU must be in center zone".into(),
        }
    }

    fn make_loop_area() -> PclConstraint {
        PclConstraint::LoopArea {
            id: "loop_1".into(),
            loop_name: "half_bridge".into(),
            max_area_mm2: 100.0,
            tier: ConstraintTier::Hard,
            because: "EMI compliance".into(),
            components: vec!["Q1".into(), "Q2".into(), "C1".into()],
        }
    }

    fn make_inferred() -> PclConstraint {
        PclConstraint::InferredSeparation {
            id: "inf_1".into(),
            source_pair: ("HighVoltage".into(), "Signal".into()),
            clearance_floor_mm: 6.0,
            layer_restriction: Some("B.Cu".into()),
            tier: ConstraintTier::Hard,
            because: "HV-LV isolation inferred from type lattice".into(),
        }
    }

    #[test]
    fn test_display_formats() {
        let adj = make_adjacent();
        assert!(format!("{adj}").contains("Q1 ↔ Q2"));
        let sep = make_separated();
        assert!(format!("{sep}").contains("‖"));
        let inf = make_inferred();
        assert!(format!("{inf}").contains("HighVoltage/Signal"));
    }

    #[test]
    fn test_variant_names() {
        assert_eq!(make_adjacent().variant_name(), "Adjacent");
        assert_eq!(make_separated().variant_name(), "Separated");
        assert_eq!(make_enclosing().variant_name(), "Enclosing");
        assert_eq!(make_aligned().variant_name(), "Aligned");
        assert_eq!(make_on_side().variant_name(), "OnSide");
        assert_eq!(make_anchored().variant_name(), "Anchored");
        assert_eq!(make_loop_area().variant_name(), "LoopArea");
        assert_eq!(make_inferred().variant_name(), "InferredSeparation");
    }

    #[test]
    fn test_tier_ordering() {
        assert!(ConstraintTier::Hard < ConstraintTier::Strong);
        assert!(ConstraintTier::Strong < ConstraintTier::Soft);
    }

    #[test]
    fn test_pcl_constraint_model_all_constraints() {
        let model = PclConstraintModel::new(
            vec![make_adjacent()],
            vec![make_inferred()],
        );
        assert_eq!(model.all_constraints().count(), 2);
    }

    #[test]
    fn test_pcl_constraint_model_is_empty() {
        let empty = PclConstraintModel::new(vec![], vec![]);
        assert!(empty.is_empty());
        let non_empty = PclConstraintModel::new(vec![make_adjacent()], vec![]);
        assert!(!non_empty.is_empty());
    }

    #[test]
    fn test_constraint_id_accessor() {
        assert_eq!(make_adjacent().id(), "adj_1");
        assert_eq!(make_separated().id(), "sep_1");
        assert_eq!(make_inferred().id(), "inf_1");
    }
}
