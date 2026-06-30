use crate::types::*;
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Board {
    pub width: f32,
    pub height: f32,
    pub components: Vec<Component>,
    pub traces: Vec<Trace>,
    pub pads: Vec<Pad>,
    pub zones: Vec<Zone>,
    pub title: Option<String>,
}

impl Board {
    pub fn new(width: f32, height: f32) -> Self {
        Self { width, height, components: vec![], traces: vec![], pads: vec![], zones: vec![], title: None }
    }

    pub fn component_by_ref(&self, ref_: &str) -> Option<&Component> {
        self.components.iter().find(|c| c.ref_ == ref_)
    }

    pub fn component_index_by_ref(&self, ref_: &str) -> Option<usize> {
        self.components.iter().position(|c| c.ref_ == ref_)
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Component {
    #[serde(rename = "ref")]
    pub ref_: String,
    pub position: Point,
    pub rotation: f32,
    pub width: f32,
    pub height: f32,
    #[serde(default)]
    pub status: ComponentStatus,
    pub zone: Option<String>,
    pub footprint: Option<String>,
    pub value: Option<String>,
    #[serde(default)]
    pub violations: Vec<String>,
    #[serde(default, rename = "component_type")]
    pub component_type: ComponentType,
    #[serde(default)]
    pub loss_contribution: Option<f32>,
    #[serde(default)]
    pub loss_breakdown: Option<std::collections::HashMap<String, f32>>,
    #[serde(default)]
    pub active_constraints: Vec<ConstraintInfo>,
    #[serde(default)]
    pub last_gradient: Option<(f32, f32)>,
    #[serde(default)]
    pub last_movement: Option<(f32, f32)>,
    #[serde(default)]
    pub last_movement_reason: Option<String>,
}

impl Component {
    pub fn bounds(&self) -> (Point, Point) {
        let (hw, hh) = (self.width / 2.0, self.height / 2.0);
        let cos = self.rotation.to_radians().cos();
        let sin = self.rotation.to_radians().sin();
        let corners = [
            Point::new(-hw, -hh),
            Point::new(hw, -hh),
            Point::new(hw, hh),
            Point::new(-hw, hh),
        ];
        let rotated: Vec<Point> = corners.iter().map(|p| {
            Point::new(
                self.position.x + p.x * cos - p.y * sin,
                self.position.y + p.x * sin + p.y * cos,
            )
        }).collect();
        let min_x = rotated.iter().map(|p| p.x).fold(f32::INFINITY, f32::min);
        let max_x = rotated.iter().map(|p| p.x).fold(f32::NEG_INFINITY, f32::max);
        let min_y = rotated.iter().map(|p| p.y).fold(f32::INFINITY, f32::min);
        let max_y = rotated.iter().map(|p| p.y).fold(f32::NEG_INFINITY, f32::max);
        (Point::new(min_x, min_y), Point::new(max_x, max_y))
    }

    pub fn contains_point(&self, point: &Point) -> bool {
        let dx = point.x - self.position.x;
        let dy = point.y - self.position.y;
        let cos = (-self.rotation).to_radians().cos();
        let sin = (-self.rotation).to_radians().sin();
        let rx = dx * cos - dy * sin;
        let ry = dx * sin + dy * cos;
        (rx.abs() <= self.width / 2.0) && (ry.abs() <= self.height / 2.0)
    }

    pub fn pin1_position(&self) -> Point {
        let hw = self.width / 2.0;
        let hh = self.height / 2.0;
        let cos = self.rotation.to_radians().cos();
        let sin = self.rotation.to_radians().sin();
        Point::new(
            self.position.x + (-hw) * cos - (-hh) * sin,
            self.position.y + (-hw) * sin + (-hh) * cos,
        )
    }

    pub fn neighbors<'a>(&self, all: &'a [Component], max_count: usize) -> Vec<(&'a Component, f32)> {
        let mut distances: Vec<(&Component, f32)> = all.iter()
            .filter(|c| c.ref_ != self.ref_)
            .map(|c| (c, self.position.distance_to(&c.position)))
            .collect();
        distances.sort_by(|a, b| a.1.partial_cmp(&b.1).unwrap_or(std::cmp::Ordering::Equal));
        distances.truncate(max_count);
        distances
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ConstraintInfo {
    pub constraint_type: String,
    pub status: ConstraintBinding,
    pub message: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Trace {
    pub start: Point,
    pub end: Point,
    #[serde(default = "default_trace_width")]
    pub width: f32,
    #[serde(default = "default_layer")]
    pub layer: String,
    pub net: Option<String>,
}

fn default_trace_width() -> f32 { 0.25 }
fn default_layer() -> String { "F.Cu".to_string() }

impl Trace {
    pub fn distance_to_point(&self, point: &Point) -> f32 {
        let d = self.end - self.start;
        let len_sq = d.x * d.x + d.y * d.y;
        if len_sq == 0.0 {
            return self.start.distance_to(point);
        }
        let t = ((point.x - self.start.x) * d.x + (point.y - self.start.y) * d.y) / len_sq;
        let t_clamped = t.max(0.0).min(1.0);
        let closest = Point::new(
            self.start.x + t_clamped * d.x,
            self.start.y + t_clamped * d.y,
        );
        closest.distance_to(point)
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Pad {
    pub position: Point,
    pub size: (f32, f32),
    #[serde(default = "default_pad_shape")]
    pub shape: PadShape,
    #[serde(default)]
    pub rotation: f32,
    #[serde(default = "default_layer")]
    pub layer: String,
    #[serde(default)]
    pub number: String,
    pub net: Option<String>,
    pub component_ref: Option<String>,
}

fn default_pad_shape() -> PadShape { PadShape::Rect }

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Zone {
    pub name: String,
    pub polygon: Vec<Point>,
    #[serde(default = "default_zone_type")]
    pub zone_type: String,
    pub color: Option<String>,
}

fn default_zone_type() -> String { "generic".to_string() }

impl Zone {
    pub fn area(&self) -> f32 {
        if self.polygon.len() < 3 {
            return 0.0;
        }
        let n = self.polygon.len();
        let mut area = 0.0f32;
        for i in 0..n {
            let j = (i + 1) % n;
            area += self.polygon[i].x * self.polygon[j].y;
            area -= self.polygon[j].x * self.polygon[i].y;
        }
        area.abs() / 2.0
    }

    pub fn fill_percentage(&self, board_width: f32, board_height: f32) -> f32 {
        let board_area = board_width * board_height;
        if board_area == 0.0 {
            return 0.0;
        }
        (self.area() / board_area) * 100.0
    }
}
