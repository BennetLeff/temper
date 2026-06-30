// BoardState geometry types for the DRC engine.
//
// Defines the complete board representation consumed by all DRC checks:
// components, nets, net classes, traces, vias, and copper zones.
// Implements rstar::RTreeObject on Component for spatial indexing.
//
// K1 schema — all geometry uses geo::Point, geo::Line, geo::Polygon.
// Distance calculations use ONLY geo::algorithm::euclidean_distance (K5).
//
// Origin: U2 of docs/plans/2026-06-30-003-feat-temper-drc-rs-engine-plan.md

use std::collections::HashMap;

use geo::{EuclideanDistance, Intersects, Line, Point, Polygon, Rect};

// ---------------------------------------------------------------------------
// LayerType
// ---------------------------------------------------------------------------

/// PCB layer identifiers used in DRC checks.
///
/// Display impl returns KiCad layer names (F.Cu, In1.Cu, In2.Cu, B.Cu).
/// Variants intentionally use KiCad naming (non-CamelCase).
#[allow(non_camel_case_types)]
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum LayerType {
    F_Cu,
    In1_Cu,
    In2_Cu,
    B_Cu,
}

impl std::fmt::Display for LayerType {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            LayerType::F_Cu => write!(f, "F.Cu"),
            LayerType::In1_Cu => write!(f, "In1.Cu"),
            LayerType::In2_Cu => write!(f, "In2.Cu"),
            LayerType::B_Cu => write!(f, "B.Cu"),
        }
    }
}

// ---------------------------------------------------------------------------
// BoardSide
// ---------------------------------------------------------------------------

/// Board side for component placement.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum BoardSide {
    Top,
    Bottom,
}

// ---------------------------------------------------------------------------
// PackageType
// ---------------------------------------------------------------------------

/// Component package classification.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum PackageType {
    Smd,
    Tht,
    Qfn,
    Qfp,
    Bga,
    Dpak,
    To247,
    To220,
    Other,
}

// ---------------------------------------------------------------------------
// NetClassRules
// ---------------------------------------------------------------------------

/// Design rules associated with a net class.
///
/// These mirror the Python `NetClassRule` dataclass in config_loader.py
/// and the K1 schema `net_class_rules` dict.
#[derive(Debug, Clone)]
pub struct NetClassRules {
    pub trace_width_mm: f64,
    pub clearance_mm: f64,
    pub creepage_mm: Option<f64>,
    pub voltage_v: Option<f64>,
    pub max_current_rating: Option<f64>,
    pub safety_category: Option<String>,
    pub required_layer: Option<String>,
    pub routing_strategy: Option<String>,
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

/// A single component (part) on the board.
///
/// The `center` field is the spatial coordinate used for rstar indexing.
#[derive(Debug, Clone)]
pub struct Component {
    pub refdes: String,
    pub center: Point<f64>,
    pub rotation: f64,
    pub side: BoardSide,
    pub width: f64,
    pub height: f64,
    pub net_class: String,
    pub power_dissipation_w: Option<f64>,
    pub package_type: PackageType,
    pub is_magnetic: bool,
    pub is_electrolytic: bool,
    pub vent_direction: Option<f64>,
    pub footprint_polygon: Option<Polygon<f64>>,
}

impl Component {
    /// Compute the axis-aligned bounding box of this component's footprint.
    pub fn footprint_bbox(&self) -> Rect<f64> {
        let half_w = self.width / 2.0;
        let half_h = self.height / 2.0;
        Rect::new(
            geo::Coord {
                x: self.center.x() - half_w,
                y: self.center.y() - half_h,
            },
            geo::Coord {
                x: self.center.x() + half_w,
                y: self.center.y() + half_h,
            },
        )
    }

    /// Minimum Euclidean edge-to-edge distance between this component and another.
    ///
    /// Uses footprint polygons when available (both sides), otherwise falls
    /// back to bounding-box edge distance.
    pub fn edge_distance_to(&self, other: &Component) -> f64 {
        match (&self.footprint_polygon, &other.footprint_polygon) {
            (Some(p1), Some(p2)) => p1.euclidean_distance(p2),
            _ => {
                let b1 = self.footprint_bbox();
                let b2 = other.footprint_bbox();
                rect_edge_distance(&b1, &b2)
            }
        }
    }

    /// Returns true if both components are on the same layer (side).
    pub fn same_layer(&self, other: &Component) -> bool {
        self.side == other.side
    }

    /// Returns true if this component's footprint polygon (or bbox) overlaps
    /// with the other component's footprint.
    pub fn overlaps(&self, other: &Component) -> bool {
        match (&self.footprint_polygon, &other.footprint_polygon) {
            (Some(p1), Some(p2)) => p1.intersects(p2),
            _ => {
                let b1 = self.footprint_bbox();
                let b2 = other.footprint_bbox();
                b1.intersects(&b2)
            }
        }
    }
}

impl rstar::RTreeObject for Component {
    type Envelope = rstar::AABB<[f64; 2]>;

    /// Returns the AABB centered on the component position.
    ///
    /// Uses the component center as the spatial coordinate for spatial
    /// queries. The envelope is a zero-area point AABB so that rstar
    /// nearest-neighbor queries work by center distance.
    fn envelope(&self) -> Self::Envelope {
        let p = [self.center.x(), self.center.y()];
        rstar::AABB::from_corners(p, p)
    }
}

/// Minimum Euclidean distance between two axis-aligned rectangles.
fn rect_edge_distance(r1: &Rect<f64>, r2: &Rect<f64>) -> f64 {
    let dx = if r1.max().x < r2.min().x {
        r2.min().x - r1.max().x
    } else if r2.max().x < r1.min().x {
        r1.min().x - r2.max().x
    } else {
        0.0
    };
    let dy = if r1.max().y < r2.min().y {
        r2.min().y - r1.max().y
    } else if r2.max().y < r1.min().y {
        r1.min().y - r2.max().y
    } else {
        0.0
    };
    (dx * dx + dy * dy).sqrt()
}

// ---------------------------------------------------------------------------
// TraceSegment
// ---------------------------------------------------------------------------

/// A routed trace composed of one or more straight-line segments.
#[derive(Debug, Clone)]
pub struct TraceSegment {
    pub net: String,
    pub layer: String,
    pub width: f64,
    pub segments: Vec<Line<f64>>,
}

// ---------------------------------------------------------------------------
// Via
// ---------------------------------------------------------------------------

/// A plated through-hole via connecting layers.
#[derive(Debug, Clone)]
pub struct Via {
    pub net: String,
    pub position: Point<f64>,
    pub drill: f64,
    pub pad: f64,
    pub from_layer: String,
    pub to_layer: String,
}

// ---------------------------------------------------------------------------
// CopperZone
// ---------------------------------------------------------------------------

/// A copper pour/fill zone on a specific layer.
#[derive(Debug, Clone)]
pub struct CopperZone {
    pub net: String,
    pub layer: String,
    pub polygon: Polygon<f64>,
}

// ---------------------------------------------------------------------------
// BoardState
// ---------------------------------------------------------------------------

/// Complete board state consumed by all DRC checks.
///
/// Mirrors the K1 schema (plan §K1):
///   - components, nets, net_classes, net_class_rules
///   - traces, vias, zones (optional, populated post-route)
///   - board dimensions
#[derive(Debug, Clone)]
pub struct BoardState {
    // Board dimensions
    pub width_mm: f64,
    pub height_mm: f64,
    pub margin_mm: f64,

    // Placement data
    pub components: Vec<Component>,

    // Net topology
    pub nets: HashMap<String, Vec<String>>,
    pub net_classes: HashMap<String, String>,
    pub net_class_rules: HashMap<String, NetClassRules>,

    // Routing data (optional, populated post-route)
    pub traces: Vec<TraceSegment>,
    pub vias: Vec<Via>,
    pub zones: Vec<CopperZone>,
}
