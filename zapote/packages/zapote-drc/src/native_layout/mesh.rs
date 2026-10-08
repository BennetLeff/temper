//! Constrained triangulation of unioned, filled native copper. Islands remain
//! separate; holes and net/layer boundaries are never bridged by proximity.
use super::{geometry, require, Result, Snapshot};
use geo::{Area, BooleanOps, Contains, Coord, Intersects, MultiPolygon, Point, Triangle};
use spade::{
    AngleLimit, ConstrainedDelaunayTriangulation, Point2, RefinementParameters, Triangulation,
};
use std::collections::BTreeMap;

#[derive(Debug)]
pub(super) struct Surface {
    pub net: String,
    pub layer: String,
    pub vertices: Vec<[f64; 2]>,
    pub triangles: Vec<[usize; 3]>,
    /// Native object UUID -> mesh nodes in its actual filled copper.
    pub contacts: BTreeMap<String, Vec<usize>>,
    pub area_mm2: f64,
}

/// Build only selected nets. `max_area` is an optional refinement criterion,
/// not a geometric tolerance; input coordinates are never snapped together.
pub(super) fn build(
    snapshot: &Snapshot,
    nets: &[&str],
    max_area: Option<f64>,
) -> Result<Vec<Surface>> {
    let mut groups: BTreeMap<_, Vec<_>> = BTreeMap::new();
    for item in &snapshot.copper {
        if nets.contains(&item.net.as_str()) {
            groups
                .entry((&item.net, &item.layer))
                .or_default()
                .push(item);
        }
    }
    let mut surfaces = vec![];
    for ((net, layer), mut objects) in groups {
        objects.sort_by_key(|c| &c.uuid);
        let mut union = MultiPolygon::new(vec![]);
        let mut contacts = vec![];
        for object in objects {
            let shape = geometry::shape(&object.polygons)?;
            union = union.union(&shape);
            if object.kind == "pad" || object.kind == "via" {
                contacts.push((object.uuid.as_str(), shape));
            }
        }
        let mut surface = triangulate(&union, &contacts, max_area)?;
        surface.net = net.clone();
        surface.layer = layer.clone();
        surfaces.push(surface);
    }
    Ok(surfaces)
}

pub(super) fn triangulate(
    shape: &MultiPolygon<f64>,
    contacts: &[(&str, MultiPolygon<f64>)],
    max_area: Option<f64>,
) -> Result<Surface> {
    if let Some(area) = max_area {
        require(area.is_finite() && area > 0., "invalid mesh area limit")?;
    }
    let mut result = Surface {
        net: String::new(),
        layer: String::new(),
        vertices: vec![],
        triangles: vec![],
        contacts: BTreeMap::new(),
        area_mm2: shape.unsigned_area(),
    };
    for island in &shape.0 {
        let mut cdt = ConstrainedDelaunayTriangulation::<Point2<f64>>::new();
        for ring in std::iter::once(island.exterior()).chain(island.interiors()) {
            let mut handles = vec![];
            for p in &ring.0 {
                handles.push(
                    cdt.insert(Point2::new(p.x, p.y))
                        .map_err(|e| e.to_string())?,
                );
            }
            for pair in handles.windows(2) {
                if pair[0] != pair[1] {
                    require(
                        !cdt.try_add_constraint(pair[0], pair[1]).is_empty(),
                        "intersecting copper mesh constraints",
                    )?;
                }
            }
        }
        // Explicit pad/via boundary vertices prevent a large zone triangle from
        // skipping a small terminal embedded inside the pour.
        for (_, contact) in contacts {
            for polygon in &contact.0 {
                for ring in std::iter::once(polygon.exterior()).chain(polygon.interiors()) {
                    for p in &ring.0 {
                        if island.intersects(&Point::from(*p)) {
                            cdt.insert(Point2::new(p.x, p.y))
                                .map_err(|e| e.to_string())?;
                        }
                    }
                }
            }
        }
        if let Some(area) = max_area {
            let refinement = cdt.refine(
                RefinementParameters::new()
                    .with_angle_limit(AngleLimit::from_deg(0.))
                    .with_max_allowed_area(area)
                    .with_max_additional_vertices(50_000)
                    .exclude_outer_faces(true),
            );
            require(
                refinement.refinement_complete,
                "copper mesh refinement budget exhausted",
            )?;
        }
        let mut ids = BTreeMap::new();
        let start = result.vertices.len();
        for face in cdt.inner_faces() {
            let points = face.positions();
            let center = Point::new(
                points.iter().map(|p| p.x).sum::<f64>() / 3.,
                points.iter().map(|p| p.y).sum::<f64>() / 3.,
            );
            if !island.contains(&center) {
                continue;
            }
            let mut tri = [0; 3];
            for (i, v) in face.vertices().iter().enumerate() {
                tri[i] = *ids.entry(v.fix().index()).or_insert_with(|| {
                    let p = v.position();
                    let index = result.vertices.len();
                    result.vertices.push([p.x, p.y]);
                    index
                });
            }
            result.triangles.push(tri);
        }
        for (uuid, contact) in contacts {
            let nodes = result.contacts.entry((*uuid).into()).or_default();
            for i in start..result.vertices.len() {
                if contact.intersects(&Point::from(result.vertices[i])) {
                    nodes.push(i);
                }
            }
        }
    }
    let area: f64 = result
        .triangles
        .iter()
        .map(|t| result.triangle(*t).unsigned_area())
        .sum();
    require(
        (area - result.area_mm2).abs() <= 1e-8 * result.area_mm2.max(1.),
        "copper triangulation area mismatch",
    )?;
    require(!result.triangles.is_empty(), "empty copper mesh")?;
    Ok(result)
}
impl Surface {
    pub fn triangle(&self, t: [usize; 3]) -> Triangle<f64> {
        let p = t.map(|i| Coord::from(self.vertices[i]));
        Triangle::new(p[0], p[1], p[2])
    }
}
