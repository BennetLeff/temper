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
#[derive(Default)]
pub enum ComponentStatus {
    #[serde(rename = "ok")]
    #[default]
    Ok,
    #[serde(rename = "warning")]
    Warning,
    #[serde(rename = "error")]
    Error,
    #[serde(rename = "fixed")]
    Fixed,
}


#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[derive(Default)]
pub enum PadShape {
    #[serde(rename = "rect")]
    #[default]
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
    pub fn parse(s: &str) -> Option<Self> {
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
#[derive(Default)]
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
    #[default]
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


#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn point_add_commutative() {
        let a = Point::new(1.0, 2.0);
        let b = Point::new(3.0, 4.0);
        let ab = a + b;
        let ba = b + a;
        assert!((ab.x - ba.x).abs() < 1e-6);
        assert!((ab.y - ba.y).abs() < 1e-6);
    }

    #[test]
    fn point_sub_is_add_negative() {
        let a = Point::new(5.0, 7.0);
        let b = Point::new(2.0, 3.0);
        let diff = a - b;
        let neg = Point::new(-b.x, -b.y);
        let sum = a + neg;
        assert!((diff.x - sum.x).abs() < 1e-6);
        assert!((diff.y - sum.y).abs() < 1e-6);
    }

    #[test]
    fn point_distance_to_self_is_zero() {
        let p = Point::new(3.0, 4.0);
        assert!(p.distance_to(&p) < 1e-6);
    }

    #[test]
    fn point_distance_satisfies_triangle_inequality() {
        let a = Point::new(0.0, 0.0);
        let b = Point::new(3.0, 4.0);
        let c = Point::new(5.0, 0.0);
        assert!(a.distance_to(&c) <= a.distance_to(&b) + b.distance_to(&c) + 1e-6);
    }

    #[test]
    fn component_type_from_ref_designator() {
        assert_eq!(ComponentType::from_ref_designator("U3"), ComponentType::Ic);
        assert_eq!(ComponentType::from_ref_designator("J1"), ComponentType::Connector);
        assert_eq!(ComponentType::from_ref_designator("P2"), ComponentType::Connector);
        assert_eq!(ComponentType::from_ref_designator("R12"), ComponentType::Resistor);
        assert_eq!(ComponentType::from_ref_designator("C5"), ComponentType::Capacitor);
        assert_eq!(ComponentType::from_ref_designator("L1"), ComponentType::Inductor);
        assert_eq!(ComponentType::from_ref_designator("D3"), ComponentType::Diode);
        assert_eq!(ComponentType::from_ref_designator("Q2"), ComponentType::Transistor);
    }

    #[test]
    fn component_type_empty_string_is_other() {
        assert_eq!(ComponentType::from_ref_designator(""), ComponentType::Other);
    }

    #[test]
    fn layer_name_round_trip() {
        for name in &["F.Cu", "In1.Cu", "In2.Cu", "B.Cu", "F.Silkscreen", "B.Silkscreen", "Edge.Cuts"] {
            let layer = LayerName::parse(name).unwrap();
            assert_eq!(layer.as_str(), *name);
        }
    }

    #[test]
    fn layer_name_is_copper() {
        assert!(LayerName::FCu.is_copper());
        assert!(LayerName::In1Cu.is_copper());
        assert!(LayerName::In2Cu.is_copper());
        assert!(LayerName::BCu.is_copper());
        assert!(!LayerName::FSilkscreen.is_copper());
        assert!(!LayerName::EdgeCuts.is_copper());
    }

    #[test]
    fn layer_name_from_unknown_is_none() {
        assert!(LayerName::parse("Unknown.Layer").is_none());
    }
}
