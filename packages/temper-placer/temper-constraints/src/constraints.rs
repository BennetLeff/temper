// Constraint types for the PCL constraint engine.
//
// Models each PCL constraint type as a Rust enum for exhaustive match
// semantics, ensuring every constraint variant is handled by every
// consumer at compile time (R4).

use nalgebra::Vector2;

// Tier enum matching Python ConstraintTier
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ConstraintTier {
    Hard = 1,
    Strong = 2,
    Soft = 3,
}

impl ConstraintTier {
    pub fn weight(&self) -> f64 {
        match self {
            ConstraintTier::Hard => 1_000_000.0,
            ConstraintTier::Strong => 1_000.0,
            ConstraintTier::Soft => 10.0,
        }
    }

    pub fn from_int(v: u8) -> Result<Self, String> {
        match v {
            1 => Ok(ConstraintTier::Hard),
            2 => Ok(ConstraintTier::Strong),
            3 => Ok(ConstraintTier::Soft),
            _ => Err(format!("Invalid constraint tier: {v}")),
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum DistanceMetric {
    EdgeToEdge,
    CenterToCenter,
    PinToPin,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Axis {
    X,
    Y,
    Major,
    Minor,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum BoardSide {
    Top,
    Bottom,
    Left,
    Right,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum EdgeType {
    Flush,
    Near,
    Overhang,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ConstraintType {
    Adjacent,
    Separated,
    Enclosing,
    Aligned,
    OnSide,
    Anchored,
    LoopArea,
}

// Constraint data variants — exhaustive enum per R4
#[derive(Debug, Clone)]
pub enum Constraint {
    Adjacent {
        a: String,
        b: String,
        max_distance_mm: f64,
        tier: ConstraintTier,
        metric: DistanceMetric,
        pin_a: Option<(f64, f64)>,
        pin_b: Option<(f64, f64)>,
    },
    Separated {
        a: String,
        b: String,
        min_distance_mm: f64,
        tier: ConstraintTier,
        metric: DistanceMetric,
    },
    Enclosing {
        outer: String,
        inner: Vec<String>,
        margin_mm: f64,
        tier: ConstraintTier,
    },
    Aligned {
        components: Vec<String>,
        axis: Axis,
        tolerance_mm: f64,
        tier: ConstraintTier,
    },
    OnSide {
        components: Vec<String>,
        side: BoardSide,
        edge: EdgeType,
        max_distance_mm: f64,
        tier: ConstraintTier,
    },
    Anchored {
        component: String,
        region: Option<(f64, f64, f64, f64)>,
        position: Option<(f64, f64)>,
        tier: ConstraintTier,
    },
    LoopArea {
        loop_name: String,
        max_area_mm2: f64,
        tier: ConstraintTier,
    },
}

impl Constraint {
    pub fn constraint_type(&self) -> ConstraintType {
        match self {
            Constraint::Adjacent { .. } => ConstraintType::Adjacent,
            Constraint::Separated { .. } => ConstraintType::Separated,
            Constraint::Enclosing { .. } => ConstraintType::Enclosing,
            Constraint::Aligned { .. } => ConstraintType::Aligned,
            Constraint::OnSide { .. } => ConstraintType::OnSide,
            Constraint::Anchored { .. } => ConstraintType::Anchored,
            Constraint::LoopArea { .. } => ConstraintType::LoopArea,
        }
    }

    pub fn tier(&self) -> ConstraintTier {
        match self {
            Constraint::Adjacent { tier, .. }
            | Constraint::Separated { tier, .. }
            | Constraint::Enclosing { tier, .. }
            | Constraint::Aligned { tier, .. }
            | Constraint::OnSide { tier, .. }
            | Constraint::Anchored { tier, .. }
            | Constraint::LoopArea { tier, .. } => *tier,
        }
    }

    pub fn weight(&self) -> f64 {
        self.tier().weight()
    }
}

// Index mapping: resolve component name -> index in positions array
pub type NameIndex = std::collections::HashMap<String, usize>;

pub fn resolve_positions(
    names: &[String],
    name_index: &NameIndex,
    positions: &[f64],
) -> Result<Vec<Vector2<f64>>, String> {
    let n = positions.len() / 2;
    let mut result = Vec::with_capacity(names.len());
    for name in names {
        let idx = name_index
            .get(name.as_str())
            .ok_or_else(|| format!("Component '{name}' not found in index"))?;
        if *idx >= n {
            return Err(format!("Component index {idx} out of bounds (n={n})"));
        }
        let x = positions[idx * 2];
        let y = positions[idx * 2 + 1];
        result.push(Vector2::new(x, y));
    }
    Ok(result)
}

/// Adapt the shared PCL IR at the legacy loss-engine edge.
///
/// This is intentionally exhaustive: adding a new IR kind requires an explicit
/// decision about whether the engine can consume it.
pub fn from_shared_ir(ir: &temper_pcl_ir::PclConstraint) -> Result<Constraint, String> {
    use temper_pcl_ir::PclConstraintKind;
    let tier = match ir.tier {
        temper_pcl_ir::ConstraintTier::Hard => ConstraintTier::Hard,
        temper_pcl_ir::ConstraintTier::Strong => ConstraintTier::Strong,
        temper_pcl_ir::ConstraintTier::Soft => ConstraintTier::Soft,
    };
    match &ir.kind {
        PclConstraintKind::Adjacent {
            a,
            b,
            max_distance_mm,
            metric,
        } => Ok(Constraint::Adjacent {
            a: a.clone(),
            b: b.clone(),
            max_distance_mm: *max_distance_mm,
            tier,
            metric: parse_metric(metric)?,
            pin_a: None,
            pin_b: None,
        }),
        PclConstraintKind::Separated {
            a,
            b,
            min_distance_mm,
            metric,
        } => Ok(Constraint::Separated {
            a: a.clone(),
            b: b.clone(),
            min_distance_mm: *min_distance_mm,
            tier,
            metric: parse_metric(metric)?,
        }),
        PclConstraintKind::Enclosing {
            outer,
            inner,
            margin_mm,
        } => Ok(Constraint::Enclosing {
            outer: outer.clone(),
            inner: inner.clone(),
            margin_mm: *margin_mm,
            tier,
        }),
        PclConstraintKind::Aligned {
            components,
            axis,
            tolerance_mm,
        } => Ok(Constraint::Aligned {
            components: components.clone(),
            axis: parse_axis(axis)?,
            tolerance_mm: *tolerance_mm,
            tier,
        }),
        PclConstraintKind::OnSide {
            components,
            side,
            edge,
            max_distance_mm,
        } => {
            let side = parse_side(side)?;
            let edge = parse_edge(edge)?;
            // The legacy engine requires a scalar. Infinity disables its finite-distance
            // penalty while preserving the shared IR edge semantics; None remains the
            // native representation for future consumers.
            Ok(Constraint::OnSide {
                components: components.clone(),
                side,
                edge,
                max_distance_mm: max_distance_mm.unwrap_or(f64::INFINITY),
                tier,
            })
        }
        PclConstraintKind::Anchored {
            component,
            region,
            position,
        } => Ok(Constraint::Anchored {
            component: component.clone(),
            region: region.map(|v| (v[0], v[1], v[2], v[3])),
            position: position.map(|v| (v[0], v[1])),
            tier,
        }),
        PclConstraintKind::LoopArea {
            loop_name,
            max_area_mm2,
        } => Ok(Constraint::LoopArea {
            loop_name: loop_name.clone(),
            max_area_mm2: *max_area_mm2,
            tier,
        }),
        PclConstraintKind::Keepout { .. } => Err(format!(
            "unsupported shared PCL constraint kind 'keepout' for loss engine (id {})",
            ir.id
        )),
    }
}

fn parse_metric(value: &str) -> Result<DistanceMetric, String> {
    match value {
        "edge_to_edge" => Ok(DistanceMetric::EdgeToEdge),
        "center_to_center" => Ok(DistanceMetric::CenterToCenter),
        "pin_to_pin" => Ok(DistanceMetric::PinToPin),
        _ => Err(format!("unsupported distance metric '{value}'")),
    }
}
fn parse_axis(value: &str) -> Result<Axis, String> {
    match value {
        "x" => Ok(Axis::X),
        "y" => Ok(Axis::Y),
        "major" => Ok(Axis::Major),
        "minor" => Ok(Axis::Minor),
        _ => Err(format!("unsupported axis '{value}'")),
    }
}
fn parse_side(value: &str) -> Result<BoardSide, String> {
    match value {
        "top" => Ok(BoardSide::Top),
        "bottom" => Ok(BoardSide::Bottom),
        "left" => Ok(BoardSide::Left),
        "right" => Ok(BoardSide::Right),
        _ => Err(format!("unsupported board side '{value}'")),
    }
}
fn parse_edge(value: &str) -> Result<EdgeType, String> {
    match value {
        "flush" => Ok(EdgeType::Flush),
        "near" => Ok(EdgeType::Near),
        "overhang" => Ok(EdgeType::Overhang),
        _ => Err(format!("unsupported edge type '{value}'")),
    }
}
