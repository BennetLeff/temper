//! Rust-owned F.Fab body geometry authority.
//!
//! This module is deliberately stricter than the legacy reporting-only
//! Python audit.  Its private fields mean a body, pose, or measured area can
//! only exist after validation.  The Boolean operation is performed only on
//! validated polygons; an AABB is a broad-phase optimization and never a
//! collision verdict.

use crate::core_graph_geometry::courtyard_global_points;
use crate::rotation_quadrant::RotationQuadrant;
use geo::{Area, BooleanOps, BoundingRect, Coord, Intersects, LineString, Polygon};
use std::fmt;
#[cfg(feature = "python")]
use temper_py_bridge;

/// The tolerance used by the existing F.Fab audit for boundary contact.
pub const AREA_TOLERANCE_MM2: f64 = 1e-6;

/// Errors returned before an invalid body can reach polygon Boolean work.
#[derive(Debug, Clone, PartialEq)]
pub enum BodyGeometryError {
    EmptyComponentReference,
    InvalidComponentReference,
    OddCoordinateCount,
    TooFewVertices,
    NonFiniteCoordinate,
    DegeneratePolygon,
    SelfIntersectingPolygon,
    InvalidPosition,
    InvalidRotation(i64),
    InvalidOverlapArea,
    BatchInputLengthMismatch,
    DuplicateComponentReference,
}

impl fmt::Display for BodyGeometryError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::EmptyComponentReference => f.write_str("component reference is empty"),
            Self::InvalidComponentReference => {
                f.write_str("component reference contains whitespace")
            }
            Self::OddCoordinateCount => f.write_str("polygon coordinate count must be even"),
            Self::TooFewVertices => f.write_str("polygon requires at least three usable vertices"),
            Self::NonFiniteCoordinate => {
                f.write_str("body geometry contains a non-finite coordinate")
            }
            Self::DegeneratePolygon => f.write_str("body polygon has zero or non-finite area"),
            Self::SelfIntersectingPolygon => {
                f.write_str("self-intersecting body polygons are unsupported")
            }
            Self::InvalidPosition => f.write_str("body pose position must be finite"),
            Self::InvalidRotation(raw) => write!(f, "rotation quadrant must be 0..=3, got {raw}"),
            Self::InvalidOverlapArea => {
                f.write_str("polygon overlap area is non-finite or negative")
            }
            Self::BatchInputLengthMismatch => {
                f.write_str("batch body inputs must have matching lengths")
            }
            Self::DuplicateComponentReference => {
                f.write_str("batch body references must be unique")
            }
        }
    }
}

impl std::error::Error for BodyGeometryError {}

/// A non-empty, whitespace-free KiCad component reference.
#[derive(Debug, Clone, PartialEq, Eq, Hash, PartialOrd, Ord)]
pub struct ComponentRef(String);

impl ComponentRef {
    pub fn new(raw: &str) -> Result<Self, BodyGeometryError> {
        if raw.is_empty() {
            return Err(BodyGeometryError::EmptyComponentReference);
        }
        if raw.chars().any(char::is_whitespace) {
            return Err(BodyGeometryError::InvalidComponentReference);
        }
        Ok(Self(raw.to_owned()))
    }

    pub fn as_str(&self) -> &str {
        &self.0
    }
}

/// A finite body coordinate.  The inner value is private so callers cannot
/// smuggle NaN or infinity into a validated polygon or pose.
#[derive(Debug, Clone, Copy, PartialEq, PartialOrd)]
pub struct FiniteCoordinate(f64);

impl FiniteCoordinate {
    pub fn new(value: f64) -> Result<Self, BodyGeometryError> {
        if value.is_finite() {
            Ok(Self(value))
        } else {
            Err(BodyGeometryError::NonFiniteCoordinate)
        }
    }

    pub fn value(self) -> f64 {
        self.0
    }
}

/// A validated finite point in millimetres.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct BodyPoint {
    x: FiniteCoordinate,
    y: FiniteCoordinate,
}

impl BodyPoint {
    fn new(x: f64, y: f64) -> Result<Self, BodyGeometryError> {
        Ok(Self {
            x: FiniteCoordinate::new(x)?,
            y: FiniteCoordinate::new(y)?,
        })
    }
}

/// A non-negative finite intersection area in square millimetres.
#[derive(Debug, Clone, Copy, PartialEq, PartialOrd)]
pub struct NonNegativeArea(f64);

impl NonNegativeArea {
    pub fn new(value: f64) -> Result<Self, BodyGeometryError> {
        if value.is_finite() && value >= 0.0 {
            Ok(Self(value))
        } else {
            Err(BodyGeometryError::InvalidOverlapArea)
        }
    }

    pub fn value(self) -> f64 {
        self.0
    }
}

/// A component pose whose rotation is a real `RotationQuadrant`, not an
/// unchecked degree/index integer.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct BodyPose {
    x: FiniteCoordinate,
    y: FiniteCoordinate,
    rotation: RotationQuadrant,
}

impl BodyPose {
    pub fn new(x: f64, y: f64, rotation_index: i64) -> Result<Self, BodyGeometryError> {
        let x = FiniteCoordinate::new(x).map_err(|_| BodyGeometryError::InvalidPosition)?;
        let y = FiniteCoordinate::new(y).map_err(|_| BodyGeometryError::InvalidPosition)?;
        let rotation = RotationQuadrant::ALL
            .into_iter()
            .find(|quadrant| quadrant.index() as i64 == rotation_index)
            .ok_or(BodyGeometryError::InvalidRotation(rotation_index))?;
        Ok(Self { x, y, rotation })
    }

    pub fn rotation(self) -> RotationQuadrant {
        self.rotation
    }
}

/// A validated simple polygon representing one component's real F.Fab body.
#[derive(Debug, Clone)]
pub struct BodyPolygon {
    component_ref: ComponentRef,
    polygon: Polygon<f64>,
}

impl BodyPolygon {
    pub fn new(
        component_ref: ComponentRef,
        raw_vertices: Vec<(f64, f64)>,
    ) -> Result<Self, BodyGeometryError> {
        let mut vertices = Vec::with_capacity(raw_vertices.len());
        for (x, y) in raw_vertices {
            let point = BodyPoint::new(x, y)?;
            if vertices
                .last()
                .is_some_and(|previous: &BodyPoint| *previous == point)
            {
                continue;
            }
            vertices.push(point);
        }
        if vertices.len() > 1 && vertices.first() == vertices.last() {
            vertices.pop();
        }
        if vertices.len() < 3 {
            return Err(BodyGeometryError::TooFewVertices);
        }

        let coords: Vec<Coord<f64>> = vertices
            .iter()
            .map(|point| Coord {
                x: point.x.value(),
                y: point.y.value(),
            })
            .collect();
        let area = signed_area(&coords).abs();
        if !area.is_finite() || area <= 0.0 {
            return Err(BodyGeometryError::DegeneratePolygon);
        }
        if has_non_adjacent_intersection(&coords) {
            return Err(BodyGeometryError::SelfIntersectingPolygon);
        }
        let mut ring = coords.clone();
        ring.push(coords[0]);
        Ok(Self {
            component_ref,
            polygon: Polygon::new(LineString::from(ring), vec![]),
        })
    }

    pub fn from_flat(
        component_ref: ComponentRef,
        coordinates: &[f64],
    ) -> Result<Self, BodyGeometryError> {
        if !coordinates.len().is_multiple_of(2) {
            return Err(BodyGeometryError::OddCoordinateCount);
        }
        let vertices = coordinates
            .chunks_exact(2)
            .map(|pair| (pair[0], pair[1]))
            .collect();
        Self::new(component_ref, vertices)
    }

    pub fn component_ref(&self) -> &ComponentRef {
        &self.component_ref
    }

    /// Transform a validated local polygon into board coordinates using the
    /// already-sanctioned KiCad `R(-theta)` kernel.  No fallback geometry is
    /// possible: only validated vertices reach this function.
    pub fn world_polygon(&self, pose: BodyPose) -> Result<Polygon<f64>, BodyGeometryError> {
        let local_coords: Vec<Coord<f64>> = self.polygon.exterior().coords().copied().collect();
        let Some(local_without_close) = local_coords.get(..local_coords.len().saturating_sub(1))
        else {
            return Err(BodyGeometryError::TooFewVertices);
        };
        let mut flat = Vec::with_capacity(local_without_close.len() * 2);
        for point in local_without_close {
            flat.push(point.x);
            flat.push(point.y);
        }
        let transformed = courtyard_global_points(
            &flat,
            pose.rotation.index() as i64,
            pose.x.value(),
            pose.y.value(),
        );
        let mut ring = Vec::with_capacity(local_without_close.len() + 1);
        for pair in transformed.chunks_exact(2) {
            ring.push(Coord {
                x: pair[0],
                y: pair[1],
            });
        }
        if ring.len() < 3
            || ring
                .iter()
                .any(|point| !point.x.is_finite() || !point.y.is_finite())
        {
            return Err(BodyGeometryError::NonFiniteCoordinate);
        }
        ring.push(ring[0]);
        Ok(Polygon::new(LineString::from(ring), vec![]))
    }
}

/// Closed physical relation between two transformed F.Fab bodies.
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum BodyRelation {
    Clear,
    BoundaryTouch,
    Overlap { area: NonNegativeArea },
}

impl BodyRelation {
    pub fn is_collision(self) -> bool {
        matches!(self, Self::Overlap { .. })
    }

    pub fn overlap_area(self) -> NonNegativeArea {
        match self {
            Self::Overlap { area } => area,
            Self::Clear | Self::BoundaryTouch => NonNegativeArea(0.0),
        }
    }
}

/// Classify physical overlap, using AABBs only as a sound broad-phase reject.
pub fn classify_body_overlap(
    body_a: &BodyPolygon,
    pose_a: BodyPose,
    body_b: &BodyPolygon,
    pose_b: BodyPose,
) -> Result<BodyRelation, BodyGeometryError> {
    let polygon_a = body_a.world_polygon(pose_a)?;
    let polygon_b = body_b.world_polygon(pose_b)?;
    classify_world_overlap(&polygon_a, &polygon_b)
}

/// Classify two already-transformed body polygons.
fn classify_world_overlap(
    polygon_a: &Polygon<f64>,
    polygon_b: &Polygon<f64>,
) -> Result<BodyRelation, BodyGeometryError> {
    let Some(bounds_a) = polygon_a.bounding_rect() else {
        return Err(BodyGeometryError::DegeneratePolygon);
    };
    let Some(bounds_b) = polygon_b.bounding_rect() else {
        return Err(BodyGeometryError::DegeneratePolygon);
    };
    if bounds_a.max().x < bounds_b.min().x
        || bounds_b.max().x < bounds_a.min().x
        || bounds_a.max().y < bounds_b.min().y
        || bounds_b.max().y < bounds_a.min().y
    {
        return Ok(BodyRelation::Clear);
    }

    let intersection = polygon_a.intersection(polygon_b);
    let area = intersection.unsigned_area();
    let area = NonNegativeArea::new(area)?;
    if area.value() > AREA_TOLERANCE_MM2 {
        return Ok(BodyRelation::Overlap { area });
    }
    if polygon_a.intersects(polygon_b) {
        Ok(BodyRelation::BoundaryTouch)
    } else {
        Ok(BodyRelation::Clear)
    }
}

fn signed_area(coords: &[Coord<f64>]) -> f64 {
    coords
        .iter()
        .zip(coords.iter().cycle().skip(1))
        .take(coords.len())
        .map(|(a, b)| a.x * b.y - b.x * a.y)
        .sum::<f64>()
        * 0.5
}

fn orientation(a: Coord<f64>, b: Coord<f64>, c: Coord<f64>) -> f64 {
    (b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x)
}

fn on_segment(a: Coord<f64>, b: Coord<f64>, p: Coord<f64>) -> bool {
    orientation(a, b, p) == 0.0
        && p.x >= a.x.min(b.x)
        && p.x <= a.x.max(b.x)
        && p.y >= a.y.min(b.y)
        && p.y <= a.y.max(b.y)
}

fn segments_intersect(a: Coord<f64>, b: Coord<f64>, c: Coord<f64>, d: Coord<f64>) -> bool {
    let ab_c = orientation(a, b, c);
    let ab_d = orientation(a, b, d);
    let cd_a = orientation(c, d, a);
    let cd_b = orientation(c, d, b);
    (ab_c > 0.0 && ab_d < 0.0 || ab_c < 0.0 && ab_d > 0.0)
        && (cd_a > 0.0 && cd_b < 0.0 || cd_a < 0.0 && cd_b > 0.0)
        || (ab_c == 0.0 && on_segment(a, b, c))
        || (ab_d == 0.0 && on_segment(a, b, d))
        || (cd_a == 0.0 && on_segment(c, d, a))
        || (cd_b == 0.0 && on_segment(c, d, b))
}

fn has_non_adjacent_intersection(coords: &[Coord<f64>]) -> bool {
    let n = coords.len();
    for i in 0..n {
        let a = coords[i];
        let b = coords[(i + 1) % n];
        for j in (i + 1)..n {
            // Adjacent edges share their endpoint by construction.  The
            // first and last edge are adjacent as well.
            if j == i + 1 || (i == 0 && j == n - 1) {
                continue;
            }
            if segments_intersect(a, b, coords[j], coords[(j + 1) % n]) {
                return true;
            }
        }
    }
    false
}

/// Thin pyo3 edge for the Rust authority.  Python supplies only primitive
/// extraction data and receives a closed relation plus its measured area; it
/// cannot construct a relation or bypass validation.
#[cfg(feature = "python")]
#[pyo3::pyfunction]
#[expect(
    clippy::too_many_arguments,
    reason = "the pyo3 boundary accepts two primitive polygon poses and mirrors the differential oracle"
)]
pub fn fab_body_overlap_py(
    ref_a: String,
    points_a: Vec<f64>,
    x_a: f64,
    y_a: f64,
    rotation_a: i64,
    ref_b: String,
    points_b: Vec<f64>,
    x_b: f64,
    y_b: f64,
    rotation_b: i64,
) -> pyo3::PyResult<(String, f64)> {
    use pyo3::exceptions::PyValueError;
    let result = temper_py_bridge::catch_unwind(|| {
        let component_a = ComponentRef::new(&ref_a)?;
        let component_b = ComponentRef::new(&ref_b)?;
        let body_a = BodyPolygon::from_flat(component_a, &points_a)?;
        let body_b = BodyPolygon::from_flat(component_b, &points_b)?;
        let pose_a = BodyPose::new(x_a, y_a, rotation_a)?;
        let pose_b = BodyPose::new(x_b, y_b, rotation_b)?;
        let relation = classify_body_overlap(&body_a, pose_a, &body_b, pose_b)?;
        let (name, area) = match relation {
            BodyRelation::Clear => ("clear", 0.0),
            BodyRelation::BoundaryTouch => ("boundary_touch", 0.0),
            BodyRelation::Overlap { area } => ("overlap", area.value()),
        };
        Ok::<(String, f64), BodyGeometryError>((name.to_owned(), area))
    })
    .map_err(temper_py_bridge::panic_to_err)?
    .map_err(|error| PyValueError::new_err(error.to_string()))?;
    Ok(result)
}

/// Validate one extracted F.Fab body without performing any pairwise work.
///
/// Returning `true` makes this useful as a direct extraction predicate while
/// still reporting the detailed validation failure through `ValueError`.
#[cfg(feature = "python")]
#[pyo3::pyfunction]
pub fn fab_body_validate_py(ref_name: String, points: Vec<f64>) -> pyo3::PyResult<bool> {
    use pyo3::exceptions::PyValueError;
    let result = temper_py_bridge::catch_unwind(|| {
        let component = ComponentRef::new(&ref_name)?;
        BodyPolygon::from_flat(component, &points).map(|_| true)
    })
    .map_err(temper_py_bridge::panic_to_err)?
    .map_err(|error| PyValueError::new_err(error.to_string()))?;
    Ok(result)
}

/// Validate and transform each body once, then classify every pair in
/// deterministic component-reference order.  Each returned item is
/// `(ref_a, ref_b, relation, overlap_area_mm2)` with `ref_a < ref_b`.
#[cfg(feature = "python")]
#[pyo3::pyfunction]
pub fn fab_body_relations_batch_py(
    refs: Vec<String>,
    points: Vec<Vec<f64>>,
    positions: Vec<(f64, f64)>,
    rotations: Vec<i64>,
) -> pyo3::PyResult<Vec<(String, String, String, f64)>> {
    use pyo3::exceptions::PyValueError;
    let result = temper_py_bridge::catch_unwind(|| {
        if refs.len() != points.len()
            || refs.len() != positions.len()
            || refs.len() != rotations.len()
        {
            return Err(BodyGeometryError::BatchInputLengthMismatch);
        }

        let mut bodies = Vec::with_capacity(refs.len());
        for (((ref_name, raw_points), (x, y)), rotation) in
            refs.into_iter().zip(points).zip(positions).zip(rotations)
        {
            let component = ComponentRef::new(&ref_name)?;
            let body = BodyPolygon::from_flat(component, &raw_points)?;
            let pose = BodyPose::new(x, y, rotation)?;
            let world = body.world_polygon(pose)?;
            bodies.push((ref_name, world));
        }
        let mut seen_refs = std::collections::HashSet::with_capacity(bodies.len());
        if bodies
            .iter()
            .any(|(ref_name, _)| !seen_refs.insert(ref_name))
        {
            return Err(BodyGeometryError::DuplicateComponentReference);
        }
        bodies.sort_by(|left, right| left.0.cmp(&right.0));

        let mut relations =
            Vec::with_capacity(bodies.len().saturating_mul(bodies.len().saturating_sub(1)) / 2);
        for (index, (ref_a, polygon_a)) in bodies.iter().enumerate() {
            for (ref_b, polygon_b) in bodies.iter().skip(index + 1) {
                let relation = classify_world_overlap(polygon_a, polygon_b)?;
                let (name, area) = match relation {
                    BodyRelation::Clear => ("clear", 0.0),
                    BodyRelation::BoundaryTouch => ("boundary_touch", 0.0),
                    BodyRelation::Overlap { area } => ("overlap", area.value()),
                };
                relations.push((ref_a.clone(), ref_b.clone(), name.to_owned(), area));
            }
        }
        Ok::<Vec<(String, String, String, f64)>, BodyGeometryError>(relations)
    })
    .map_err(temper_py_bridge::panic_to_err)?
    .map_err(|error| PyValueError::new_err(error.to_string()))?;
    Ok(result)
}

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

    fn square(ref_name: &str, half: f64) -> BodyPolygon {
        BodyPolygon::new(
            ComponentRef::new(ref_name).unwrap(),
            vec![(-half, -half), (half, -half), (half, half), (-half, half)],
        )
        .unwrap()
    }

    #[cfg_attr(test, test)]
    fn rejects_invalid_geometry_and_unvalidated_pose_values() {
        assert!(ComponentRef::new("").is_err());
        assert!(
            BodyPolygon::new(
                ComponentRef::new("A").unwrap(),
                vec![(0.0, 0.0), (1.0, 0.0)],
            )
            .is_err()
        );
        assert!(
            BodyPolygon::new(
                ComponentRef::new("A").unwrap(),
                vec![(0.0, 0.0), (f64::NAN, 1.0), (1.0, 0.0)],
            )
            .is_err()
        );
        assert!(BodyPose::new(0.0, 0.0, 4).is_err());
        assert!(BodyPose::new(0.0, f64::INFINITY, 0).is_err());
        assert!(NonNegativeArea::new(-1.0).is_err());
        assert!(NonNegativeArea::new(f64::NAN).is_err());
        assert!(
            BodyPolygon::new(
                ComponentRef::new("A").unwrap(),
                vec![(0.0, 0.0), (2.0, 2.0), (0.0, 2.0), (2.0, 0.0)],
            )
            .is_err()
        );
    }

    #[cfg_attr(test, test)]
    fn aabb_overlap_without_polygon_overlap_is_clear() {
        let a = BodyPolygon::new(
            ComponentRef::new("A").unwrap(),
            vec![(0.0, 0.0), (4.0, 0.0), (0.0, 4.0)],
        )
        .unwrap();
        let b = BodyPolygon::new(
            ComponentRef::new("B").unwrap(),
            vec![(4.0, 4.0), (8.0, 4.0), (4.0, 8.0)],
        )
        .unwrap();
        let relation = classify_body_overlap(
            &a,
            BodyPose::new(0.0, 0.0, 0).unwrap(),
            &b,
            BodyPose::new(0.0, 0.0, 0).unwrap(),
        )
        .unwrap();
        assert_eq!(relation, BodyRelation::Clear);
    }

    #[cfg_attr(test, test)]
    fn true_overlap_reports_finite_non_negative_area() {
        let a = square("A", 1.0);
        let b = square("B", 1.0);
        let relation = classify_body_overlap(
            &a,
            BodyPose::new(0.0, 0.0, 0).unwrap(),
            &b,
            BodyPose::new(0.5, 0.0, 0).unwrap(),
        )
        .unwrap();
        match relation {
            BodyRelation::Overlap { area } => assert!(area.value() > 0.0),
            other => panic!("expected overlap, got {other:?}"),
        }
    }

    #[cfg_attr(test, test)]
    fn boundary_touch_is_not_a_physical_collision() {
        let a = square("A", 1.0);
        let b = square("B", 1.0);
        let relation = classify_body_overlap(
            &a,
            BodyPose::new(0.0, 0.0, 0).unwrap(),
            &b,
            BodyPose::new(2.0, 0.0, 0).unwrap(),
        )
        .unwrap();
        assert_eq!(relation, BodyRelation::BoundaryTouch);
        assert!(!relation.is_collision());
    }

    #[cfg_attr(test, test)]
    fn asymmetric_quadrant_uses_kicad_r_minus_theta() {
        let body = BodyPolygon::new(
            ComponentRef::new("A").unwrap(),
            vec![(10.0, 4.0), (11.0, 4.0), (11.0, 5.0)],
        )
        .unwrap();
        let world = body
            .world_polygon(BodyPose::new(0.0, 0.0, 1).unwrap())
            .unwrap();
        let first = world.exterior().coords().next().unwrap();
        assert!((first.x - 4.0).abs() < 1e-9);
        assert!((first.y + 10.0).abs() < 1e-9);
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        (
            "body_collision::tests::rejects_invalid_geometry_and_unvalidated_pose_values",
            rejects_invalid_geometry_and_unvalidated_pose_values,
        ),
        (
            "body_collision::tests::aabb_overlap_without_polygon_overlap_is_clear",
            aabb_overlap_without_polygon_overlap_is_clear,
        ),
        (
            "body_collision::tests::true_overlap_reports_finite_non_negative_area",
            true_overlap_reports_finite_non_negative_area,
        ),
        (
            "body_collision::tests::boundary_touch_is_not_a_physical_collision",
            boundary_touch_is_not_a_physical_collision,
        ),
        (
            "body_collision::tests::asymmetric_quadrant_uses_kicad_r_minus_theta",
            asymmetric_quadrant_uses_kicad_r_minus_theta,
        ),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}
