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
    #[serde(default)]
    pub drill_polygon: Option<Polygon>,
}

#[derive(Clone, Debug, serde::Serialize, serde::Deserialize)]
pub struct DrillHole {
    pub id: String,
    pub center_mm: [f64; 2],
    pub diameter_mm: f64,
    #[serde(default)]
    pub polygon: Option<Polygon>,
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

/// Per-rule population accounting owned by P2. `CheckReport` is shared by
/// every Zapote unit and intentionally keeps its historical shape; callers
/// that need object-level completeness can consume this separate value.
#[derive(Clone, Debug, Default, serde::Serialize, serde::Deserialize, PartialEq, Eq)]
pub struct P2Population {
    pub evaluated: std::collections::BTreeMap<String, Vec<String>>,
    pub skipped: std::collections::BTreeMap<String, Vec<String>>,
}

impl P2Population {
    fn candidate(&mut self, rule: &str, id: String) {
        self.skipped.entry(rule.into()).or_default().push(id);
    }
    fn evaluated(&mut self, rule: &str, id: String) {
        self.skipped.get_mut(rule).unwrap().retain(|v| v != &id);
        self.evaluated.get_mut(rule).unwrap().push(id);
    }
    fn candidates(input: &ManufacturingInput) -> Self {
        let mut result = Self::default();
        for rule in [BODY, RING, DRILL, OUTLINE, ANGLE] {
            result.evaluated.insert(rule.into(), vec![]);
            result.skipped.insert(rule.into(), vec![]);
        }
        for (i, a) in input.bodies.iter().enumerate() {
            result.candidate(ANGLE, format!("{}#{i}", a.component));
            for (j, b) in input.bodies.iter().enumerate().skip(i + 1) {
                result.candidate(BODY, format!("{}#{i} / {}#{j}", a.component, b.component));
            }
        }
        for pad in &input.pads {
            result.candidate(RING, pad.id.clone());
        }
        for (i, a) in input.holes.iter().enumerate() {
            for b in input.holes.iter().skip(i + 1) {
                result.candidate(DRILL, format!("{} / {}", a.id, b.id));
            }
        }
        for copper in &input.copper {
            result.candidate(OUTLINE, copper.id.clone());
        }
        result
    }
}

/// Existing callers retain the report-only API; both APIs execute the same loops.
pub fn validate(input: &ManufacturingInput) -> CheckReport {
    validate_with_population(input).0
}

const BODY: &str = "DRC.P2.BODY_COLLISION";
const RING: &str = "DRC.P2.ANNULAR_RING";
const DRILL: &str = "DRC.P2.DRILL_CONFLICT";
const OUTLINE: &str = "DRC.P2.COPPER_OUTLINE";
const ANGLE: &str = "DRC.P2.SUPPORTED_ANGLE";

pub fn validate_with_population(input: &ManufacturingInput) -> (CheckReport, P2Population) {
    let mut population = P2Population::candidates(input);
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
    let polygons = std::iter::once(&input.outline)
        .chain(input.cutouts.iter())
        .chain(input.copper.iter().map(|c| &c.polygon))
        .chain(input.bodies.iter().map(|b| &b.local_polygon))
        .chain(input.pads.iter().map(|p| &p.copper))
        .chain(input.pads.iter().filter_map(|p| p.drill_polygon.as_ref()))
        .chain(input.holes.iter().filter_map(|h| h.polygon.as_ref()));
    if polygons
        .into_iter()
        .any(|p| p.vertices_mm.len() < 3 || p.vertices_mm.iter().flatten().any(|v| !v.is_finite()))
        || input
            .bodies
            .iter()
            .any(|b| b.position_mm.iter().any(|v| !v.is_finite()))
        || [
            input.limits.minimum_annular_ring_mm,
            input.limits.minimum_hole_clearance_mm,
        ]
        .iter()
        .any(|v| !v.is_finite() || *v < 0.0)
        || input.holes.iter().any(|h| {
            !h.diameter_mm.is_finite()
                || h.diameter_mm <= 0.0
                || h.center_mm.iter().any(|v| !v.is_finite())
        })
    {
        findings.push(Finding::fail(
            "DRC.P2.INPUT_GEOMETRY",
            "malformed polygon, drill, or fabrication limit",
            &input.board_id,
        ));
        return (
            CheckReport::from_findings(findings, checked, gaps),
            population,
        );
    }
    let mut world = Vec::new();
    for (body_index, body) in input.bodies.iter().enumerate() {
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
        population.evaluated(ANGLE, format!("{}#{body_index}", body.component));
        world.push((
            body.component.as_str(),
            transform(&body.local_polygon, body.position_mm, body.rotation_deg),
            body_index,
        ));
    }
    for i in 0..world.len() {
        for j in (i + 1)..world.len() {
            if world[i].0 == world[j].0 {
                continue;
            }
            population.evaluated(
                BODY,
                format!(
                    "{}#{} / {}#{}",
                    world[i].0, world[i].2, world[j].0, world[j].2
                ),
            );
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
        if !pad.plated || (pad.drill_mm.is_none() && pad.drill_polygon.is_none()) {
            continue;
        }
        let ring = if let Some(drill) = &pad.drill_polygon {
            if !polygon_inside(drill, &pad.copper) {
                -1.0
            } else {
                boundary_distance(drill, &pad.copper)
            }
        } else {
            let Some(center) = pad.drill_center_mm else {
                findings.push(indeterminate(
                    RING,
                    "plated pad has no native drill center",
                    &pad.id,
                ));
                continue;
            };
            let drill = pad.drill_mm.unwrap();
            if !drill.is_finite() || drill <= 0.0 || !point_in(center, &pad.copper) {
                -1.0
            } else {
                min_boundary_distance(center, &pad.copper) - drill / 2.0
            }
        };
        population.evaluated(RING, pad.id.clone());
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
            let gap = match (&a.polygon, &b.polygon) {
                (Some(ap), Some(bp)) if polygons_intersect(ap, bp) => -1.0,
                (Some(ap), Some(bp)) => boundary_distance(ap, bp),
                (None, None) => {
                    distance(a.center_mm, b.center_mm) - (a.diameter_mm + b.diameter_mm) / 2.0
                }
                _ => {
                    findings.push(indeterminate(
                        DRILL,
                        "mixed native and scalar drill evidence",
                        format!("{} / {}", a.id, b.id),
                    ));
                    continue;
                }
            };
            population.evaluated(DRILL, format!("{} / {}", a.id, b.id));
            if !gap.is_finite() || gap < input.limits.minimum_hole_clearance_mm {
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
        population.evaluated(OUTLINE, copper.id.clone());
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
    (
        CheckReport::from_findings(findings, checked, gaps),
        population,
    )
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
    if a.vertices_mm.len() < 3 || b.vertices_mm.len() < 3 {
        return false;
    }
    // Endpoints alone miss an edge crossing a concave board notch.
    a.vertices_mm.iter().all(|p| point_in(*p, b)) && !edges_cross(a, b)
}
fn edges_cross(a: &Polygon, b: &Polygon) -> bool {
    (0..a.vertices_mm.len()).any(|i| {
        (0..b.vertices_mm.len()).any(|j| {
            segments_intersect(
                a.vertices_mm[i],
                a.vertices_mm[(i + 1) % a.vertices_mm.len()],
                b.vertices_mm[j],
                b.vertices_mm[(j + 1) % b.vertices_mm.len()],
            )
        })
    })
}
fn boundary_distance(a: &Polygon, b: &Polygon) -> f64 {
    a.vertices_mm
        .iter()
        .map(|p| min_boundary_distance(*p, b))
        .chain(b.vertices_mm.iter().map(|p| min_boundary_distance(*p, a)))
        .fold(f64::INFINITY, f64::min)
}
fn polygons_intersect(a: &Polygon, b: &Polygon) -> bool {
    if a.vertices_mm.is_empty() || b.vertices_mm.is_empty() {
        return false;
    }
    if a.vertices_mm.iter().any(|p| point_in(*p, b))
        || b.vertices_mm.iter().any(|p| point_in(*p, a))
    {
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
                drill_polygon: None,
            }],
            holes: vec![DrillHole {
                id: "H1".into(),
                center_mm: [7., 7.],
                diameter_mm: 0.5,
                polygon: None,
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
    fn population_reports_rule_objects_without_changing_check_report() {
        let mut i = base();
        i.pads.push(PadGeometry {
            id: "J1.2".into(),
            copper: rect(2., 0., 1., 1.),
            drill_mm: None,
            drill_center_mm: None,
            plated: false,
            drill_polygon: None,
        });
        let (_, p) = validate_with_population(&i);
        assert_eq!(p.evaluated[RING], vec!["J1.1"]);
        assert_eq!(p.skipped[RING], vec!["J1.2"]);
        assert!(p.evaluated[BODY].is_empty());
        assert_eq!(p.evaluated[OUTLINE], vec!["T1"]);
        assert!(p.evaluated[DRILL].is_empty());
        assert_eq!(p.evaluated[ANGLE], vec!["U1#0"]);
    }

    #[test]
    fn population_tracks_actual_early_returns_and_pair_skips() {
        let mut i = base();
        i.bodies.push(i.bodies[0].clone());
        i.holes.push(DrillHole {
            id: "H2".into(),
            center_mm: [8., 8.],
            diameter_mm: 0.5,
            polygon: Some(rect(8., 8., 0.5, 0.5)),
        });
        i.pads[0].drill_center_mm = None;
        let (_, p) = validate_with_population(&i);
        assert!(p.evaluated[BODY].is_empty());
        assert_eq!(p.skipped[BODY], vec!["U1#0 / U1#1"]);
        assert!(p.evaluated[DRILL].is_empty());
        assert_eq!(p.skipped[DRILL], vec!["H1 / H2"]);
        assert!(p.evaluated[RING].is_empty());
        assert_eq!(p.skipped[RING], vec!["J1.1"]);
        i.outline.vertices_mm.clear();
        let (report, p) = validate_with_population(&i);
        assert_eq!(report.status, Status::Fail);
        assert!(p.evaluated.values().all(Vec::is_empty));
        assert_eq!(p.skipped[OUTLINE], vec!["T1"]);
        let mut invalid_pose = base();
        invalid_pose.bodies[0].position_mm[0] = f64::NAN;
        let (report, population) = validate_with_population(&invalid_pose);
        assert_eq!(report.status, Status::Fail);
        assert!(population.evaluated.values().all(Vec::is_empty));
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
            polygon: None,
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
    #[test]
    fn drill_outside_copper_cannot_have_positive_annular_ring() {
        let mut i = base();
        i.pads[0].drill_center_mm = Some([10., 10.]);
        assert!(validate(&i)
            .findings
            .iter()
            .any(|f| f.rule == RING && f.status == Status::Fail));
    }
    #[test]
    fn empty_polygon_nan_and_negative_limits_are_not_success() {
        for mutation in 0..3 {
            let mut i = base();
            assert_eq!(validate(&i).status, Status::Pass);
            match mutation {
                0 => i.copper[0].polygon.vertices_mm.clear(),
                1 => i.holes[0].diameter_mm = f64::NAN,
                _ => i.limits.minimum_hole_clearance_mm = -1.,
            };
            assert_eq!(validate(&i).status, Status::Fail);
        }
    }
    #[test]
    fn edge_between_inside_vertices_cannot_cross_concave_notch() {
        let outline = Polygon {
            vertices_mm: vec![
                [0., 0.],
                [10., 0.],
                [10., 10.],
                [6., 10.],
                [6., 4.],
                [4., 4.],
                [4., 10.],
                [0., 10.],
            ],
        };
        assert!(!polygon_inside(&rect(2., 2., 6., 6.), &outline));
    }
    #[test]
    fn slotted_holes_use_native_polygon_not_round_width() {
        let mut i = base();
        i.holes[0].polygon = Some(rect(6., 6., 3., 0.5));
        i.holes.push(DrillHole {
            id: "slot2".into(),
            center_mm: [9., 6.],
            diameter_mm: 0.2,
            polygon: Some(rect(8.5, 6., 3., 0.5)),
        });
        assert!(validate(&i)
            .findings
            .iter()
            .any(|f| f.rule == DRILL && f.status == Status::Fail));
    }

    #[test]
    fn native_fractured_zone_hole_matches_pcbnew_membership() {
        let oracle: serde_json::Value =
            serde_json::from_str(include_str!("../../../validation/p2/hole-oracle.json")).unwrap();
        let polygons: Vec<Polygon> = serde_json::from_value(oracle["polygons"].clone()).unwrap();
        for probe in oracle["probes"].as_array().unwrap() {
            let point = serde_json::from_value(probe["point"].clone()).unwrap();
            assert_eq!(
                polygons.iter().any(|p| point_in(point, p)),
                probe["inside"].as_bool().unwrap()
            );
        }
        assert!(!polygons_intersect(&polygons[0], &rect(4., 4., 2., 2.)));
    }
}
