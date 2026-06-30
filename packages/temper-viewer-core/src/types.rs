use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct Point {
    pub x: f32,
    pub y: f32,
}

impl Point {
    pub const fn new(x: f32, y: f32) -> Self {
        Self { x, y }
    }

    pub fn distance_to(&self, other: &Point) -> f32 {
        ((self.x - other.x).powi(2) + (self.y - other.y).powi(2)).sqrt()
    }

    pub fn to_vec2(&self) -> glam::Vec2 {
        glam::Vec2::new(self.x, self.y)
    }

    pub fn from_vec2(v: glam::Vec2) -> Self {
        Self { x: v.x, y: v.y }
    }
}

impl std::ops::Add for Point {
    type Output = Self;
    fn add(self, rhs: Self) -> Self {
        Self { x: self.x + rhs.x, y: self.y + rhs.y }
    }
}

impl std::ops::Sub for Point {
    type Output = Self;
    fn sub(self, rhs: Self) -> Self {
        Self { x: self.x - rhs.x, y: self.y - rhs.y }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum ComponentStatus {
    #[serde(rename = "ok")]
    Ok,
    #[serde(rename = "warning")]
    Warning,
    #[serde(rename = "error")]
    Error,
    #[serde(rename = "fixed")]
    Fixed,
}

impl Default for ComponentStatus {
    fn default() -> Self {
        Self::Ok
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum PadShape {
    #[serde(rename = "rect")]
    Rect,
    #[serde(rename = "circle")]
    Circle,
    #[serde(rename = "oval")]
    Oval,
    #[serde(rename = "roundrect")]
    RoundRect,
    #[serde(rename = "custom")]
    Custom,
}

impl Default for PadShape {
    fn default() -> Self {
        Self::Rect
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum ConstraintBinding {
    #[serde(rename = "ok")]
    Ok,
    #[serde(rename = "warning")]
    Warning,
    #[serde(rename = "error")]
    Error,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum LayerName {
    #[serde(rename = "F.Cu")]
    FCu,
    #[serde(rename = "In1.Cu")]
    In1Cu,
    #[serde(rename = "In2.Cu")]
    In2Cu,
    #[serde(rename = "B.Cu")]
    BCu,
    #[serde(rename = "F.Silkscreen")]
    FSilkscreen,
    #[serde(rename = "B.Silkscreen")]
    BSilkscreen,
    #[serde(rename = "Edge.Cuts")]
    EdgeCuts,
}

impl LayerName {
    pub fn from_str(s: &str) -> Option<Self> {
        match s {
            "F.Cu" => Some(Self::FCu),
            "In1.Cu" => Some(Self::In1Cu),
            "In2.Cu" => Some(Self::In2Cu),
            "B.Cu" => Some(Self::BCu),
            "F.Silkscreen" => Some(Self::FSilkscreen),
            "B.Silkscreen" => Some(Self::BSilkscreen),
            "Edge.Cuts" => Some(Self::EdgeCuts),
            _ => None,
        }
    }

    pub fn as_str(&self) -> &'static str {
        match self {
            Self::FCu => "F.Cu",
            Self::In1Cu => "In1.Cu",
            Self::In2Cu => "In2.Cu",
            Self::BCu => "B.Cu",
            Self::FSilkscreen => "F.Silkscreen",
            Self::BSilkscreen => "B.Silkscreen",
            Self::EdgeCuts => "Edge.Cuts",
        }
    }

    pub fn is_copper(&self) -> bool {
        matches!(self, Self::FCu | Self::In1Cu | Self::In2Cu | Self::BCu)
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum ComponentType {
    #[serde(rename = "ic")]
    Ic,
    #[serde(rename = "connector")]
    Connector,
    #[serde(rename = "resistor")]
    Resistor,
    #[serde(rename = "capacitor")]
    Capacitor,
    #[serde(rename = "inductor")]
    Inductor,
    #[serde(rename = "diode")]
    Diode,
    #[serde(rename = "transistor")]
    Transistor,
    #[serde(rename = "other")]
    Other,
}

impl ComponentType {
    pub fn from_ref_designator(ref_: &str) -> Self {
        if ref_.is_empty() {
            return Self::Other;
        }
        match ref_.chars().next().unwrap() {
            'U' => Self::Ic,
            'J' | 'P' => Self::Connector,
            'R' => Self::Resistor,
            'C' => Self::Capacitor,
            'L' => Self::Inductor,
            'D' => Self::Diode,
            'Q' => Self::Transistor,
            _ => Self::Other,
        }
    }
}

impl Default for ComponentType {
    fn default() -> Self {
        Self::Other
    }
}
