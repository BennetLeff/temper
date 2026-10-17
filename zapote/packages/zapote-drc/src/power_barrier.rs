//! Conservative plan-view copper barrier over the saved KiCad filled-copper census.
//! This screen includes cross-layer pairs. It does not qualify package insulation.

use serde::{Deserialize, Serialize};
use std::collections::BTreeSet;

const SCHEMA: &str = "temper.power-stage-120v.copper-evidence.v1";

#[derive(Debug, Deserialize)]
pub struct Input {
    pub evidence: Evidence,
    pub domains: Domains,
    pub floor_mm: f64,
}

#[derive(Debug, Deserialize)]
pub struct Domains {
    pub selv: Vec<String>,
    pub hot: Vec<String>,
    pub pe: Vec<String>,
}

#[derive(Debug, Deserialize)]
pub struct Evidence {
    schema: String,
    board_sha256: String,
    copper_layers: Vec<String>,
    census: Census,
    items: Vec<Item>,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct Census {
    footprints: usize,
    pads: usize,
    tracks: usize,
    vias: usize,
    zones: usize,
    filled_zone_polygons: usize,
    items: usize,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct Item {
    kind: String,
    net: String,
    layers: Vec<String>,
    #[serde(rename = "ref")]
    reference: Option<String>,
    #[serde(rename = "box")]
    bounds: Option<[f64; 4]>,
    centre: Option<[f64; 2]>,
    radius: Option<f64>,
    start: Option<[f64; 2]>,
    end: Option<[f64; 2]>,
    width: Option<f64>,
    polygon: Option<Vec<[f64; 2]>>,
}

#[derive(Debug)]
enum Core {
    Point([f64; 2]),
    Segment([f64; 2], [f64; 2]),
    Polygon(Vec<[f64; 2]>),
}

#[derive(Debug)]
struct Copper {
    kind: String,
    net: String,
    layers: Vec<String>,
    reference: Option<String>,
    core: Core,
    radius: f64,
    bounds: [f64; 4],
    domain: Domain,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Domain {
    Barrier,
    Hot,
}

type WorstEntry = (
    f64,
    String,
    String,
    Vec<String>,
    String,
    String,
    Vec<String>,
    bool,
);
type DomainSets<'a> = (BTreeSet<&'a str>, BTreeSet<&'a str>, BTreeSet<&'a str>);

#[derive(Debug, Serialize)]
pub struct Report {
    floor_mm: f64,
    board_sha256: String,
    census: Census,
    violations: usize,
    cross_layer: usize,
    worst: Vec<WorstEntry>,
}

fn valid_point(point: [f64; 2]) -> bool {
    point.iter().all(|value| value.is_finite() && value.abs() <= 1.0e6)
}

fn core_bounds(core: &Core, radius: f64) -> [f64; 4] {
    let mut bounds = [
        f64::INFINITY,
        f64::INFINITY,
        f64::NEG_INFINITY,
        f64::NEG_INFINITY,
    ];
    let mut include = |p: &[f64; 2]| {
        bounds[0] = bounds[0].min(p[0] - radius);
        bounds[1] = bounds[1].min(p[1] - radius);
        bounds[2] = bounds[2].max(p[0] + radius);
        bounds[3] = bounds[3].max(p[1] + radius);
    };
    match core {
        Core::Point(p) => include(p),
        Core::Segment(a, b) => {
            include(a);
            include(b);
        }
        Core::Polygon(vertices) => {
            for p in vertices {
                include(p);
            }
        }
    }
    bounds
}

fn domain_sets(domains: &Domains) -> Result<DomainSets<'_>, String> {
    let selv: BTreeSet<_> = domains.selv.iter().map(String::as_str).collect();
    let hot: BTreeSet<_> = domains.hot.iter().map(String::as_str).collect();
    let pe: BTreeSet<_> = domains.pe.iter().map(String::as_str).collect();
    if selv.len() != domains.selv.len()
        || hot.len() != domains.hot.len()
        || pe.len() != domains.pe.len()
        || selv.is_empty()
        || hot.is_empty()
        || pe.is_empty()
        || selv
            .iter()
            .chain(hot.iter())
            .chain(pe.iter())
            .any(|net| net.is_empty())
        || !selv.is_disjoint(&hot)
        || !selv.is_disjoint(&pe)
        || !hot.is_disjoint(&pe)
    {
        return Err("barrier domains must be nonempty, unique and disjoint".into());
    }
    Ok((selv, hot, pe))
}

fn make_copper(
    item: Item,
    layers: &BTreeSet<&str>,
    domains: &DomainSets<'_>,
) -> Result<Copper, String> {
    if item.net.is_empty()
        || item.layers.is_empty()
        || item
            .layers
            .iter()
            .any(|layer| !layers.contains(layer.as_str()))
        || item.layers.iter().collect::<BTreeSet<_>>().len() != item.layers.len()
    {
        return Err(format!(
            "invalid layers or net on copper item {}",
            item.kind
        ));
    }
    let domain = if domains.0.contains(item.net.as_str()) || domains.2.contains(item.net.as_str()) {
        Domain::Barrier
    } else if domains.1.contains(item.net.as_str()) {
        Domain::Hot
    } else {
        return Err(format!("unclassified copper net: {}", item.net));
    };
    let core;
    let radius;
    match item.kind.as_str() {
        "pad" => {
            if item.centre.is_some()
                || item.radius.is_some()
                || item.start.is_some()
                || item.end.is_some()
                || item.width.is_some()
                || item.polygon.is_some()
            {
                return Err("pad carries unsupported extra geometry".into());
            }
            let b = item.bounds.ok_or("pad lacks bounds")?;
            if !b.iter().all(|v| v.is_finite() && v.abs() <= 1.0e6)
                || b[0] >= b[2]
                || b[1] >= b[3]
                || item
                    .reference
                    .as_ref()
                    .is_none_or(|r| r.split_once('.').is_none())
            {
                return Err("invalid pad bounds or reference".into());
            }
            core = Core::Polygon(vec![[b[0], b[1]], [b[2], b[1]], [b[2], b[3]], [b[0], b[3]]]);
            radius = 0.0;
        }
        "via" => {
            if item.bounds.is_some()
                || item.reference.is_some()
                || item.start.is_some()
                || item.end.is_some()
                || item.width.is_some()
                || item.polygon.is_some()
            {
                return Err("via carries unsupported extra geometry".into());
            }
            let p = item.centre.ok_or("via lacks centre")?;
            radius = item.radius.ok_or("via lacks radius")?;
            if !valid_point(p)
                || !radius.is_finite()
                || radius <= 0.0
                || item.layers.len() != layers.len()
            {
                return Err("invalid through-via geometry".into());
            }
            core = Core::Point(p);
        }
        "track" => {
            if item.bounds.is_some()
                || item.reference.is_some()
                || item.centre.is_some()
                || item.radius.is_some()
                || item.polygon.is_some()
            {
                return Err("track carries unsupported extra geometry".into());
            }
            let a = item.start.ok_or("track lacks start")?;
            let b = item.end.ok_or("track lacks end")?;
            radius = item.width.ok_or("track lacks width")? / 2.0;
            if !valid_point(a)
                || !valid_point(b)
                || !radius.is_finite()
                || radius <= 0.0
                || item.layers.len() != 1
            {
                return Err("invalid track geometry".into());
            }
            core = Core::Segment(a, b);
        }
        "zone" => {
            if item.bounds.is_some()
                || item.reference.is_some()
                || item.centre.is_some()
                || item.radius.is_some()
                || item.start.is_some()
                || item.end.is_some()
                || item.width.is_some()
            {
                return Err("zone carries unsupported extra geometry".into());
            }
            let points = item.polygon.ok_or("zone lacks filled polygon")?;
            if points.len() < 3
                || points.iter().any(|p| !valid_point(*p))
                || item.layers.len() != 1
                || !has_noncollinear_vertices(&points)
            {
                return Err("invalid filled-zone polygon".into());
            }
            core = Core::Polygon(points);
            radius = 0.0;
        }
        other => return Err(format!("unsupported copper item kinds: {other}")),
    }
    let bounds = core_bounds(&core, radius);
    if !bounds.iter().all(|value| value.is_finite() && value.abs() <= 1.0e6) {
        return Err("copper bounds exceed the supported board-coordinate range".into());
    }
    Ok(Copper {
        kind: item.kind,
        net: item.net,
        layers: item.layers,
        reference: item.reference,
        core,
        radius,
        bounds,
        domain,
    })
}

fn cross(a: [f64; 2], b: [f64; 2], c: [f64; 2]) -> f64 {
    (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
}

fn has_noncollinear_vertices(points: &[[f64; 2]]) -> bool {
    points
        .windows(3)
        .any(|p| cross(p[0], p[1], p[2]).abs() > 1e-12)
        || cross(
            points[points.len() - 2],
            points[points.len() - 1],
            points[0],
        )
        .abs()
            > 1e-12
}

fn point_segment_distance(p: [f64; 2], a: [f64; 2], b: [f64; 2]) -> f64 {
    let dx = b[0] - a[0];
    let dy = b[1] - a[1];
    let length = dx * dx + dy * dy;
    let t = if length > 0.0 {
        ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / length
    } else {
        0.0
    }
    .clamp(0.0, 1.0);
    (p[0] - a[0] - t * dx).hypot(p[1] - a[1] - t * dy)
}

fn on_segment(a: [f64; 2], b: [f64; 2], p: [f64; 2]) -> bool {
    cross(a, b, p).abs() <= 1e-10
        && p[0] >= a[0].min(b[0]) - 1e-10
        && p[0] <= a[0].max(b[0]) + 1e-10
        && p[1] >= a[1].min(b[1]) - 1e-10
        && p[1] <= a[1].max(b[1]) + 1e-10
}

fn segments_intersect(a: [f64; 2], b: [f64; 2], c: [f64; 2], d: [f64; 2]) -> bool {
    let ab_c = cross(a, b, c);
    let ab_d = cross(a, b, d);
    let cd_a = cross(c, d, a);
    let cd_b = cross(c, d, b);
    ((ab_c > 0.0 && ab_d < 0.0) || (ab_c < 0.0 && ab_d > 0.0))
        && ((cd_a > 0.0 && cd_b < 0.0) || (cd_a < 0.0 && cd_b > 0.0))
        || on_segment(a, b, c)
        || on_segment(a, b, d)
        || on_segment(c, d, a)
        || on_segment(c, d, b)
}

fn segment_distance(a: [f64; 2], b: [f64; 2], c: [f64; 2], d: [f64; 2]) -> f64 {
    if segments_intersect(a, b, c, d) {
        return 0.0;
    }
    point_segment_distance(a, c, d)
        .min(point_segment_distance(b, c, d))
        .min(point_segment_distance(c, a, b))
        .min(point_segment_distance(d, a, b))
}

fn edges(points: &[[f64; 2]]) -> impl Iterator<Item = ([f64; 2], [f64; 2])> + '_ {
    (0..points.len()).map(|i| (points[i], points[(i + 1) % points.len()]))
}

fn point_in_polygon(point: [f64; 2], points: &[[f64; 2]]) -> bool {
    let mut parity = false;
    let mut winding = 0i32;
    for (a, b) in edges(points) {
        if on_segment(a, b, point) {
            return true;
        }
        if (a[1] > point[1]) != (b[1] > point[1]) {
            let x = a[0] + (point[1] - a[1]) * (b[0] - a[0]) / (b[1] - a[1]);
            if point[0] < x {
                parity = !parity;
            }
        }
        if a[1] <= point[1] && b[1] > point[1] && cross(a, b, point) > 0.0 {
            winding += 1;
        }
        if a[1] > point[1] && b[1] <= point[1] && cross(a, b, point) < 0.0 {
            winding -= 1;
        }
    }
    // The union is conservative at touching/slit contours: no lobe is lost.
    parity || winding != 0
}

fn point_polygon_distance(p: [f64; 2], poly: &[[f64; 2]]) -> f64 {
    if point_in_polygon(p, poly) {
        return 0.0;
    }
    edges(poly)
        .map(|(a, b)| point_segment_distance(p, a, b))
        .fold(f64::INFINITY, f64::min)
}

fn segment_polygon_distance(a: [f64; 2], b: [f64; 2], poly: &[[f64; 2]]) -> f64 {
    if point_in_polygon(a, poly) || point_in_polygon(b, poly) {
        return 0.0;
    }
    edges(poly)
        .map(|(c, d)| segment_distance(a, b, c, d))
        .fold(f64::INFINITY, f64::min)
}

fn polygon_polygon_distance(a: &[[f64; 2]], b: &[[f64; 2]]) -> f64 {
    if a.iter().any(|p| point_in_polygon(*p, b)) || b.iter().any(|p| point_in_polygon(*p, a)) {
        return 0.0;
    }
    edges(a)
        .flat_map(|(p, q)| edges(b).map(move |(r, s)| segment_distance(p, q, r, s)))
        .fold(f64::INFINITY, f64::min)
}

fn core_distance(a: &Core, b: &Core) -> f64 {
    match (a, b) {
        (Core::Point(a), Core::Point(b)) => (a[0] - b[0]).hypot(a[1] - b[1]),
        (Core::Point(p), Core::Segment(a, b)) | (Core::Segment(a, b), Core::Point(p)) => {
            point_segment_distance(*p, *a, *b)
        }
        (Core::Point(p), Core::Polygon(poly)) | (Core::Polygon(poly), Core::Point(p)) => {
            point_polygon_distance(*p, poly)
        }
        (Core::Segment(a, b), Core::Segment(c, d)) => segment_distance(*a, *b, *c, *d),
        (Core::Segment(a, b), Core::Polygon(poly)) | (Core::Polygon(poly), Core::Segment(a, b)) => {
            segment_polygon_distance(*a, *b, poly)
        }
        (Core::Polygon(a), Core::Polygon(b)) => polygon_polygon_distance(a, b),
    }
}

fn bounds_gap(a: [f64; 4], b: [f64; 4]) -> f64 {
    let dx = (a[0] - b[2]).max(b[0] - a[2]).max(0.0);
    let dy = (a[1] - b[3]).max(b[1] - a[3]).max(0.0);
    dx.hypot(dy)
}

fn label(item: &Copper) -> String {
    item.reference.clone().unwrap_or_else(|| item.kind.clone())
}

fn same_component_pads(a: &Copper, b: &Copper) -> bool {
    if a.kind != "pad" || b.kind != "pad" {
        return false;
    }
    match (&a.reference, &b.reference) {
        (Some(a), Some(b)) => a.split_once('.').map(|v| v.0) == b.split_once('.').map(|v| v.0),
        _ => false,
    }
}

pub fn check(input: Input) -> Result<Report, String> {
    if input.evidence.schema != SCHEMA {
        return Err("unsupported or legacy copper evidence schema".into());
    }
    if input.evidence.board_sha256.len() != 64
        || !input
            .evidence
            .board_sha256
            .bytes()
            .all(|b| b.is_ascii_hexdigit())
    {
        return Err("invalid board digest".into());
    }
    if !input.floor_mm.is_finite() || input.floor_mm <= 0.0 {
        return Err("barrier floor must be positive and finite".into());
    }
    let layers: BTreeSet<_> = input
        .evidence
        .copper_layers
        .iter()
        .map(String::as_str)
        .collect();
    if layers.is_empty()
        || layers.len() != input.evidence.copper_layers.len()
        || layers.iter().any(|s| s.is_empty())
    {
        return Err("invalid copper-layer census".into());
    }
    let domains = domain_sets(&input.domains)?;
    let mut counts = [0usize; 4];
    let mut items = Vec::with_capacity(input.evidence.items.len());
    for item in input.evidence.items {
        let copper = make_copper(item, &layers, &domains)?;
        counts[match copper.kind.as_str() {
            "pad" => 0,
            "track" => 1,
            "via" => 2,
            "zone" => 3,
            _ => unreachable!(),
        }] += 1;
        items.push(copper);
    }
    let census = &input.evidence.census;
    if census.footprints == 0
        || counts[0] == 0
        || census.pads != counts[0]
        || census.tracks != counts[1]
        || census.vias != counts[2]
        || census.filled_zone_polygons != counts[3]
        || census.zones > counts[3]
        || census.items != items.len()
    {
        return Err("copper item census disagrees with exported items".into());
    }
    let barrier: Vec<_> = items
        .iter()
        .filter(|item| item.domain == Domain::Barrier)
        .collect();
    let hot: Vec<_> = items
        .iter()
        .filter(|item| item.domain == Domain::Hot)
        .collect();
    if barrier.is_empty() || hot.is_empty() {
        return Err("missing barrier or HOT copper".into());
    }
    let mut worst = Vec::new();
    for first in barrier {
        for second in &hot {
            if same_component_pads(first, second)
                || bounds_gap(first.bounds, second.bounds) >= input.floor_mm
            {
                continue;
            }
            let gap =
                (core_distance(&first.core, &second.core) - first.radius - second.radius).max(0.0);
            if gap < input.floor_mm {
                let same_layer = first
                    .layers
                    .iter()
                    .any(|layer| second.layers.contains(layer));
                worst.push((
                    ((gap * 100.0).round() / 100.0),
                    label(first),
                    first.net.clone(),
                    first.layers.clone(),
                    label(second),
                    second.net.clone(),
                    second.layers.clone(),
                    same_layer,
                ));
            }
        }
    }
    worst.sort_by(|a, b| {
        a.0.total_cmp(&b.0)
            .then_with(|| a.1.cmp(&b.1))
            .then_with(|| a.2.cmp(&b.2))
            .then_with(|| a.3.cmp(&b.3))
            .then_with(|| a.4.cmp(&b.4))
            .then_with(|| a.5.cmp(&b.5))
            .then_with(|| a.6.cmp(&b.6))
            .then_with(|| a.7.cmp(&b.7))
    });
    let violations = worst.len();
    let cross_layer = worst.iter().filter(|entry| !entry.7).count();
    worst.truncate(25);
    Ok(Report {
        floor_mm: input.floor_mm,
        board_sha256: input.evidence.board_sha256,
        census: input.evidence.census,
        violations,
        cross_layer,
        worst,
    })
}

#[cfg(test)]
mod tests {
    use super::{check, Input};
    use serde_json::{json, Value};

    fn input(items: Vec<Value>) -> Input {
        let pads = items.iter().filter(|item| item["kind"] == "pad").count();
        let tracks = items.iter().filter(|item| item["kind"] == "track").count();
        let vias = items.iter().filter(|item| item["kind"] == "via").count();
        let zones = items.iter().filter(|item| item["kind"] == "zone").count();
        serde_json::from_value(json!({
            "evidence": {"schema": "temper.power-stage-120v.copper-evidence.v1",
                "board_sha256": "0".repeat(64), "copper_layers": ["F.Cu", "B.Cu"],
                "census": {"footprints": 2, "pads": pads, "tracks": tracks,
                    "vias": vias, "zones": zones, "filled_zone_polygons": zones,
                    "items": items.len()}, "items": items},
            "domains": {"selv": ["SEL"], "hot": ["HOT"], "pe": ["PE"]},
            "floor_mm": 8.0
        }))
        .unwrap()
    }

    #[test]
    fn exact_circle_to_rectangle_gap_counts_cross_layer_pair() {
        let pad = json!({"kind":"pad", "ref":"U1.1", "net":"SEL",
            "layers":["F.Cu"], "box":[0.0,0.0,1.0,1.0]});
        let via = |x: f64| {
            json!({"kind":"via", "net":"HOT",
            "layers":["F.Cu","B.Cu"], "centre":[x,0.5], "radius":1.0})
        };
        assert_eq!(
            check(input(vec![pad.clone(), via(10.0)]))
                .unwrap()
                .violations,
            0
        );
        let report = check(input(vec![pad, via(9.99)])).unwrap();
        assert_eq!(report.violations, 1);
        assert_eq!(report.worst[0].0, 7.99);
    }

    #[test]
    fn opposite_layer_track_crossing_is_not_discarded() {
        let pad = json!({"kind":"pad", "ref":"U1.1", "net":"SEL",
            "layers":["F.Cu"], "box":[0.0,0.0,1.0,1.0]});
        let track = json!({"kind":"track", "net":"HOT", "layers":["B.Cu"],
            "start":[-1.0,0.5], "end":[2.0,0.5], "width":0.2});
        let report = check(input(vec![pad, track])).unwrap();
        assert_eq!((report.violations, report.cross_layer), (1, 1));
    }

    #[test]
    fn touching_zone_contour_keeps_both_lobes() {
        let zone = json!({"kind":"zone", "net":"SEL", "layers":["F.Cu"],
            "polygon":[[0.0,0.0],[2.0,0.0],[2.0,2.0],[0.0,2.0],
                       [0.0,0.0],[-2.0,0.0],[-2.0,-2.0],[0.0,-2.0]]});
        let pad = json!({"kind":"pad", "ref":"R1.1", "net":"HOT",
            "layers":["B.Cu"], "box":[-1.5,-1.5,-0.5,-0.5]});
        let mut with_pad = input(vec![zone, pad]);
        with_pad.floor_mm = 0.2;
        let report = check(with_pad).unwrap();
        assert_eq!((report.violations, report.cross_layer), (1, 1));
    }

    #[test]
    fn same_package_pad_exception_does_not_cover_other_copper() {
        let selv = json!({"kind":"pad", "ref":"U1.1", "net":"SEL",
            "layers":["F.Cu"], "box":[0.0,0.0,1.0,1.0]});
        let hot_pad = json!({"kind":"pad", "ref":"U1.2", "net":"HOT",
            "layers":["F.Cu"], "box":[2.0,0.0,3.0,1.0]});
        assert_eq!(
            check(input(vec![selv.clone(), hot_pad]))
                .unwrap()
                .violations,
            0
        );
        let hot_trace = json!({"kind":"track", "net":"HOT", "layers":["F.Cu"],
            "start":[2.0,0.5], "end":[3.0,0.5], "width":0.2});
        assert_eq!(check(input(vec![selv, hot_trace])).unwrap().violations, 1);
    }

    #[test]
    fn malformed_or_unclassified_copper_fails_closed() {
        let pad = json!({"kind":"pad", "ref":"U1.1", "net":"SEL",
            "layers":["F.Cu"], "box":[0.0,0.0,1.0,1.0]});
        let unknown = json!({"kind":"via", "net":"OTHER", "layers":["F.Cu","B.Cu"],
            "centre":[10.0,0.0], "radius":0.5});
        assert!(check(input(vec![pad.clone(), unknown]))
            .unwrap_err()
            .contains("unclassified"));
        let bad_zone = json!({"kind":"zone", "net":"HOT", "layers":["F.Cu"],
            "polygon":[[0.0,0.0],[1.0,0.0],[2.0,0.0]]});
        assert!(check(input(vec![pad, bad_zone]))
            .unwrap_err()
            .contains("invalid filled-zone"));
    }
}
