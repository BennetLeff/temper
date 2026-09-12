//! Exact mechanical and manufacturing checks over native KiCad geometry.
//!
//! The adapter is intentionally outside this module: callers must provide the
//! exported F.Fab/courtyard, Edge.Cuts, copper and drill polygons.  A bounding
//! box or component dimension is never substituted for missing geometry.

use std::f64::consts::PI;
use zapote_core::{CheckReport, Finding, Status};

#[derive(Clone, Debug, serde::Serialize, serde::Deserialize)]
pub struct ManufacturingInput {
    pub board_id: String,
    pub bodies: Vec<Body>,
    pub pads: Vec<PadGeometry>,
    pub holes: Vec<DrillHole>,
    pub copper: Vec<CopperPolygon>,
    pub outline: Polygon,
    pub cutouts: Vec<Polygon>,
    pub limits: FabricationLimits,
    pub angle_policy: AnglePolicy,
    #[serde(default)]
    pub unsupported: Vec<String>,
}

#[derive(Clone, Debug, serde::Serialize, serde::Deserialize)]
pub struct Body {
    pub component: String,
    pub local_polygon: Polygon,
    pub position_mm: [f64; 2],
    pub rotation_deg: f64,
    pub required: bool,
}

#[derive(Clone, Debug, serde::Serialize, serde::Deserialize)]
pub struct PadGeometry {
    pub id: String,
    pub copper: Polygon,
    pub drill_mm: Option<f64>,
    pub drill_center_mm: Option<[f64; 2]>,
    pub plated: bool,
}

#[derive(Clone, Debug, serde::Serialize, serde::Deserialize)]
pub struct DrillHole {
    pub id: String,
    pub center_mm: [f64; 2],
    pub diameter_mm: f64,
}

#[derive(Clone, Debug, serde::Serialize, serde::Deserialize)]
pub struct CopperPolygon {
    pub id: String,
    pub polygon: Polygon,
    pub layer: String,
}

#[derive(Clone, Debug, serde::Serialize, serde::Deserialize)]
pub struct Polygon {
    pub vertices_mm: Vec<[f64; 2]>,
}

#[derive(Clone, Debug, serde::Serialize, serde::Deserialize)]
pub struct FabricationLimits {
    /// The source-declared prototype envelope. Values are not vendor claims.
    pub name: String,
    pub source: String,
    pub qualified: bool,
    pub minimum_annular_ring_mm: f64,
    pub minimum_hole_clearance_mm: f64,
    pub assembly_process: String,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, serde::Serialize, serde::Deserialize)]
pub enum AnglePolicy {
    Arbitrary,
    QuadrantsOnly,
}

const BODY: &str = "DRC.P2.BODY_COLLISION";
const RING: &str = "DRC.P2.ANNULAR_RING";
const DRILL: &str = "DRC.P2.DRILL_CONFLICT";
const OUTLINE: &str = "DRC.P2.COPPER_OUTLINE";
const ANGLE: &str = "DRC.P2.SUPPORTED_ANGLE";

pub fn validate(input: &ManufacturingInput) -> CheckReport {
    let mut findings = Vec::new();
    let mut checked = vec![
        BODY.into(),
        RING.into(),
        DRILL.into(),
        OUTLINE.into(),
        ANGLE.into(),
    ];
    let mut gaps = Vec::new();
    if input.board_id.trim().is_empty() {
        gaps.push("board identity is required".into());
    }
    for item in &input.unsupported {
        gaps.push(format!("unsupported native geometry: {item}"));
    }
    if input.outline.vertices_mm.len() < 3 {
        gaps.push("native Edge.Cuts outline is required".into());
    }
    if input.limits.name.trim().is_empty() || input.limits.source.trim().is_empty() {
        gaps.push("source-declared fabrication limits are required".into());
    }
    if !input.limits.qualified {
        gaps.push(format!(
            "fabrication envelope '{}' is prototype/source-declared, not fabrication-qualified",
            input.limits.name
        ));
    }
    if input.limits.assembly_process.trim().is_empty() {
        gaps.push("assembly process is required".into());
    }
    if input
        .bodies
        .iter()
        .any(|b| b.required && b.local_polygon.vertices_mm.len() < 3)
    {
        findings.push(indeterminate(
            BODY,
            "required body has no native polygon",
            "required-body",
        ));
    }
    let mut world = Vec::new();
    for body in &input.bodies {
        if body.local_polygon.vertices_mm.len() < 3 {
            continue;
        }
        if !body.rotation_deg.is_finite() {
            findings.push(indeterminate(
                ANGLE,
                "body rotation is not finite",
                &body.component,
            ));
            continue;
        }
        if input.angle_policy == AnglePolicy::QuadrantsOnly && !is_quadrant(body.rotation_deg) {
            findings.push(indeterminate(
                ANGLE,
                "native body pose uses an angle outside the supported quadrant pose API",
                &body.component,
            ));
            continue;
        }
        world.push((
            body.component.as_str(),
            transform(&body.local_polygon, body.position_mm, body.rotation_deg),
        ));
    }
    for i in 0..world.len() {
        for j in (i + 1)..world.len() {
            if polygons_intersect(&world[i].1, &world[j].1) {
                findings.push(finding(
                    BODY,
                    format!(
                        "exact F.Fab polygons overlap for {} and {}",
                        world[i].0, world[j].0
                    ),
                    format!("{} / {}", world[i].0, world[j].0),
                    "overlap",
                    "clear",
                ));
            }
        }
    }
    if input.bodies.is_empty() {
        findings.push(indeterminate(
            BODY,
            "required body population is empty; no body acceptance is possible",
            "bodies",
        ));
    }

    for pad in &input.pads {
        if !pad.plated || pad.drill_mm.is_none() {
            continue;
        }
        let drill = pad.drill_mm.unwrap();
        let Some(center) = pad.drill_center_mm else {
            findings.push(indeterminate(
                RING,
                "plated pad has no native drill center",
                &pad.id,
            ));
            continue;
        };
        let ring = min_boundary_distance(center, &pad.copper) - drill / 2.0;
        if !ring.is_finite() || ring < input.limits.minimum_annular_ring_mm {
            findings.push(finding(
                RING,
                "minimum annular ring is below the source-declared limit",
                &pad.id,
                format!("{ring:.3} mm"),
                format!(">= {:.3} mm", input.limits.minimum_annular_ring_mm),
            ));
        }
    }
    if input.holes.len() < 2 {
        checked.push("DRC.P2.DRILL_CONFLICT.POPULATION".into());
    }
    for i in 0..input.holes.len() {
        for j in (i + 1)..input.holes.len() {
            let a = &input.holes[i];
            let b = &input.holes[j];
            let gap = distance(a.center_mm, b.center_mm) - (a.diameter_mm + b.diameter_mm) / 2.0;
            if gap < input.limits.minimum_hole_clearance_mm {
                findings.push(finding(
                    DRILL,
                    "drill-to-drill clearance is below the source-declared limit",
                    format!("{} / {}", a.id, b.id),
                    format!("{gap:.3} mm"),
                    format!(">= {:.3} mm", input.limits.minimum_hole_clearance_mm),
                ));
            }
        }
    }
    for copper in &input.copper {
        if !polygon_inside(&copper.polygon, &input.outline)
            || input
                .cutouts
                .iter()
                .any(|hole| polygons_intersect(&copper.polygon, hole))
        {
            findings.push(finding(
                OUTLINE,
                format!(
                    "{} copper crosses native Edge.Cuts or a cutout",
                    copper.layer
                ),
                &copper.id,
                "outside/intersects",
                "inside outline and clear of cutouts",
            ));
        }
    }
    if input.copper.is_empty() {
        findings.push(indeterminate(
            OUTLINE,
            "native copper population is empty",
            "copper",
        ));
    }
    if !input.limits.qualified {
        findings.push(indeterminate("DRC.P2.FABRICATION_QUALIFICATION", "mechanical findings use source-declared prototype limits; vendor/process qualification is pending", "fabrication-envelope"));
    }
    CheckReport::from_findings(findings, checked, gaps)
}

fn indeterminate(rule: &str, message: impl Into<String>, object: impl Into<String>) -> Finding {
    Finding::indeterminate(rule, message, object)
}
fn finding(
    rule: &str,
    message: impl Into<String>,
    object: impl Into<String>,
    actual: impl Into<String>,
    required: impl Into<String>,
) -> Finding {
    Finding {
        rule: rule.into(),
        severity: "error".into(),
        status: Status::Fail,
        message: message.into(),
        object: object.into(),
        actual: Some(actual.into()),
        required: Some(required.into()),
    }
}
fn min_boundary_distance(point: [f64; 2], p: &Polygon) -> f64 {
    p.vertices_mm
        .iter()
        .enumerate()
        .map(|(i, &a)| {
            point_segment_distance(point, a, p.vertices_mm[(i + 1) % p.vertices_mm.len()])
        })
        .fold(f64::INFINITY, f64::min)
}
fn point_segment_distance(p: [f64; 2], a: [f64; 2], b: [f64; 2]) -> f64 {
    let dx = b[0] - a[0];
    let dy = b[1] - a[1];
    let denom = dx * dx + dy * dy;
    let t = if denom > 0.0 {
        (((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / denom).clamp(0.0, 1.0)
    } else {
        0.0
    };
    distance(p, [a[0] + t * dx, a[1] + t * dy])
}
fn transform(p: &Polygon, pos: [f64; 2], degrees: f64) -> Polygon {
    let r = -degrees * PI / 180.0;
    let (s, c) = r.sin_cos();
    Polygon {
        vertices_mm: p
            .vertices_mm
            .iter()
            .map(|q| [pos[0] + c * q[0] - s * q[1], pos[1] + s * q[0] + c * q[1]])
            .collect(),
    }
}
fn is_quadrant(a: f64) -> bool {
    let q = (a / 90.0).round();
    (a - q * 90.0).abs() < 1e-7
}
fn distance(a: [f64; 2], b: [f64; 2]) -> f64 {
    ((a[0] - b[0]).powi(2) + (a[1] - b[1]).powi(2)).sqrt()
}
fn point_in(p: [f64; 2], poly: &Polygon) -> bool {
    let mut inside = false;
    for i in 0..poly.vertices_mm.len() {
        let a = poly.vertices_mm[i];
        let b = poly.vertices_mm[(i + 1) % poly.vertices_mm.len()];
        if ((a[1] > p[1]) != (b[1] > p[1]))
            && p[0] < (b[0] - a[0]) * (p[1] - a[1]) / (b[1] - a[1]) + a[0]
        {
            inside = !inside;
        }
    }
    inside
}
fn polygon_inside(a: &Polygon, b: &Polygon) -> bool {
    a.vertices_mm.iter().all(|p| point_in(*p, b))
}
fn polygons_intersect(a: &Polygon, b: &Polygon) -> bool {
    if polygon_inside(a, b) || polygon_inside(b, a) {
        return true;
    }
    for i in 0..a.vertices_mm.len() {
        for j in 0..b.vertices_mm.len() {
            if segments_intersect(
                a.vertices_mm[i],
                a.vertices_mm[(i + 1) % a.vertices_mm.len()],
                b.vertices_mm[j],
                b.vertices_mm[(j + 1) % b.vertices_mm.len()],
            ) {
                return true;
            }
        }
    }
    false
}
fn orient(a: [f64; 2], b: [f64; 2], c: [f64; 2]) -> f64 {
    (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
}
fn segments_intersect(a: [f64; 2], b: [f64; 2], c: [f64; 2], d: [f64; 2]) -> bool {
    let o1 = orient(a, b, c);
    let o2 = orient(a, b, d);
    let o3 = orient(c, d, a);
    let o4 = orient(c, d, b);
    (o1 == 0.0 && on(a, b, c))
        || (o2 == 0.0 && on(a, b, d))
        || (o3 == 0.0 && on(c, d, a))
        || (o4 == 0.0 && on(c, d, b))
        || (o1.signum() != o2.signum() && o3.signum() != o4.signum())
}
fn on(a: [f64; 2], b: [f64; 2], p: [f64; 2]) -> bool {
    p[0] >= a[0].min(b[0]) - 1e-9
        && p[0] <= a[0].max(b[0]) + 1e-9
        && p[1] >= a[1].min(b[1]) - 1e-9
        && p[1] <= a[1].max(b[1]) + 1e-9
}

#[cfg(test)]
mod tests {
    use super::*;
    fn rect(x: f64, y: f64, w: f64, h: f64) -> Polygon {
        Polygon {
            vertices_mm: vec![[x, y], [x + w, y], [x + w, y + h], [x, y + h]],
        }
    }
    fn base() -> ManufacturingInput {
        ManufacturingInput {
            board_id: "unit".into(),
            bodies: vec![Body {
                component: "U1".into(),
                local_polygon: rect(-1., -1., 2., 2.),
                position_mm: [3., 3.],
                rotation_deg: 0.,
                required: true,
            }],
            pads: vec![PadGeometry {
                id: "J1.1".into(),
                copper: rect(0., 0., 1., 1.),
                drill_mm: Some(0.4),
                drill_center_mm: Some([0.5, 0.5]),
                plated: true,
            }],
            holes: vec![DrillHole {
                id: "H1".into(),
                center_mm: [7., 7.],
                diameter_mm: 0.5,
            }],
            copper: vec![CopperPolygon {
                id: "T1".into(),
                polygon: rect(2., 2., 2., 1.),
                layer: "F.Cu".into(),
            }],
            outline: rect(0., 0., 10., 10.),
            cutouts: vec![],
            limits: FabricationLimits {
                name: "prototype".into(),
                source: "unit contract".into(),
                qualified: true,
                minimum_annular_ring_mm: 0.2,
                minimum_hole_clearance_mm: 0.2,
                assembly_process: "reflow".into(),
            },
            angle_policy: AnglePolicy::Arbitrary,
            unsupported: vec![],
        }
    }
    #[test]
    fn passing_baseline_has_no_findings() {
        let mut i = base();
        i.pads[0].copper = rect(0., 0., 1., 1.);
        assert_eq!(validate(&i).status, Status::Pass);
    }
    #[test]
    fn body_collision_is_exact_and_object_identified() {
        let mut i = base();
        i.bodies.push(Body {
            component: "U2".into(),
            local_polygon: rect(-1., -1., 2., 2.),
            position_mm: [3.5, 3.],
            rotation_deg: 0.,
            required: true,
        });
        let r = validate(&i);
        assert!(r
            .findings
            .iter()
            .any(|f| f.rule == BODY && f.object.contains("U1")));
    }
    #[test]
    fn undersized_ring_fails_with_actual_and_required() {
        let mut input = base();
        input.pads[0].copper = rect(0.0, 0.0, 0.6, 0.6);
        let r = validate(&input);
        let f = r.findings.iter().find(|f| f.rule == RING).unwrap();
        assert!(f.actual.is_some() && f.required.is_some());
    }
    #[test]
    fn drill_conflict_is_detected() {
        let mut i = base();
        i.holes.push(DrillHole {
            id: "H2".into(),
            center_mm: [7.3, 7.],
            diameter_mm: 0.5,
        });
        assert!(validate(&i).findings.iter().any(|f| f.rule == DRILL));
    }
    #[test]
    fn outline_crossing_is_detected() {
        let mut i = base();
        i.copper[0].polygon = rect(9., 9., 2., 1.);
        assert!(validate(&i).findings.iter().any(|f| f.rule == OUTLINE));
    }
    #[test]
    fn missing_body_is_indeterminate() {
        let mut i = base();
        i.bodies.clear();
        assert_eq!(validate(&i).status, Status::Indeterminate);
    }
    #[test]
    fn unsupported_angle_is_indeterminate_under_quadrant_policy() {
        let mut i = base();
        i.angle_policy = AnglePolicy::QuadrantsOnly;
        i.bodies[0].rotation_deg = 30.;
        assert!(validate(&i)
            .findings
            .iter()
            .any(|f| f.rule == ANGLE && f.status == Status::Indeterminate));
    }
}
