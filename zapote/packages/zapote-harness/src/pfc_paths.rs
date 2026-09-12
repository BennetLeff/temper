//! Native copper binding for the PFC current envelope model.
//!
//! This module deliberately only uses geometry which the native exporter
//! supplied.  In particular, a pad is not connected to a track merely because
//! its bounding boxes overlap: the exporter gives us a centre point and this
//! adapter requires a centre hit (or reports a coverage gap).

use std::collections::BTreeMap;
use zapote_core::unit::UnitNativeEvidence;
use zapote_drc::power_branches::{Edge, Graph};

const EPS: f64 = 1e-5;
const MODELED_COMPONENTS: &[&str] = &[
    "mains", "holder", "cmc", "ntc", "bypass", "bridge", "l_boost", "q_boost", "d_boost", "c1",
    "c2", "c3", "c4", "c_hf", "output", "shunt",
];

#[derive(Debug, Clone)]
pub struct BoundGraph {
    pub graph: Graph,
    pub terminal_nodes: BTreeMap<String, usize>,
    pub edge_width_mm: BTreeMap<String, f64>,
    pub edge_kind: BTreeMap<String, String>,
    pub coverage_gaps: Vec<String>,
    pub uncertified_nets: std::collections::BTreeSet<String>,
}

#[derive(Clone, Copy, Debug, PartialEq)]
struct Point([f64; 2]);

impl Point {
    fn dist2(self, other: Self) -> f64 {
        (self.0[0] - other.0[0]).powi(2) + (self.0[1] - other.0[1]).powi(2)
    }
}

fn point_on(a: Point, b: Point, p: Point) -> Option<f64> {
    let dx = b.0[0] - a.0[0];
    let dy = b.0[1] - a.0[1];
    let len2 = dx * dx + dy * dy;
    if len2 <= EPS * EPS {
        return None;
    }
    let t = ((p.0[0] - a.0[0]) * dx + (p.0[1] - a.0[1]) * dy) / len2;
    let q = Point([a.0[0] + t * dx, a.0[1] + t * dy]);
    ((-EPS..=1.0 + EPS).contains(&t) && q.dist2(p) <= EPS * EPS).then_some(t.clamp(0.0, 1.0))
}

fn point_segment_distance(a: Point, b: Point, p: Point) -> f64 {
    let dx = b.0[0] - a.0[0];
    let dy = b.0[1] - a.0[1];
    let len2 = dx * dx + dy * dy;
    let t = if len2 <= EPS * EPS {
        0.0
    } else {
        (((p.0[0] - a.0[0]) * dx + (p.0[1] - a.0[1]) * dy) / len2).clamp(0.0, 1.0)
    };
    Point([a.0[0] + t * dx, a.0[1] + t * dy]).dist2(p).sqrt()
}

fn intersection(a: Point, b: Point, c: Point, d: Point) -> Option<Point> {
    let (rx, ry) = (b.0[0] - a.0[0], b.0[1] - a.0[1]);
    let (sx, sy) = (d.0[0] - c.0[0], d.0[1] - c.0[1]);
    let den = rx * sy - ry * sx;
    if den.abs() <= EPS {
        return None;
    }
    let qpx = c.0[0] - a.0[0];
    let qpy = c.0[1] - a.0[1];
    let t = (qpx * sy - qpy * sx) / den;
    let u = (qpx * ry - qpy * rx) / den;
    ((-EPS..=1.0 + EPS).contains(&t) && (-EPS..=1.0 + EPS).contains(&u))
        .then_some(Point([a.0[0] + t * rx, a.0[1] + t * ry]))
}

fn copper(layer: &str) -> bool {
    layer == "F.Cu" || layer == "B.Cu" || layer.ends_with(".Cu")
}

// A split straight track has exactly the same copper as the unsplit track.
// Coalesce only equal-width, collinear, touching spans for the side-contact
// diagnostic. The current graph retains every original native UUID/segment.
fn side_contact_spans(traces: &[zapote_core::Trace]) -> Vec<zapote_core::Trace> {
    let mut spans: Vec<_> = traces
        .iter()
        .flat_map(|t| {
            t.points_mm.windows(2).map(|w| zapote_core::Trace {
                id: t.id.clone(),
                net: t.net.clone(),
                layer: t.layer.clone(),
                width_mm: t.width_mm,
                points_mm: w.to_vec(),
            })
        })
        .collect();
    spans.sort_by(|a, b| a.id.cmp(&b.id));
    loop {
        let mut merged = false;
        'search: for i in 0..spans.len() {
            for j in i + 1..spans.len() {
                let (a, b) = (&spans[i], &spans[j]);
                if a.net != b.net || a.layer != b.layer || a.width_mm != b.width_mm {
                    continue;
                }
                let p = a.points_mm[0];
                let dx = a.points_mm[1][0] - p[0];
                let dy = a.points_mm[1][1] - p[1];
                let length = dx.hypot(dy);
                if length <= EPS {
                    continue;
                }
                if b.points_mm
                    .iter()
                    .any(|q| ((q[0] - p[0]) * dy - (q[1] - p[1]) * dx).abs() / length > EPS)
                {
                    continue;
                }
                let project = |q: [f64; 2]| ((q[0] - p[0]) * dx + (q[1] - p[1]) * dy) / length;
                let (first, last) = (project(b.points_mm[0]), project(b.points_mm[1]));
                let lo = first.min(last);
                let hi = first.max(last);
                if lo > length + EPS || hi < -EPS {
                    continue;
                }
                let start = lo.min(0.);
                let end = hi.max(length);
                let id = format!("{}+{}", a.id, b.id);
                spans[i].points_mm = vec![
                    [p[0] + start * dx / length, p[1] + start * dy / length],
                    [p[0] + end * dx / length, p[1] + end * dy / length],
                ];
                spans[i].id = id;
                spans.remove(j);
                merged = true;
                break 'search;
            }
        }
        if !merged {
            return spans;
        }
    }
}
fn key(net: &str, layer: &str, p: Point) -> (String, String, i64, i64) {
    (
        net.into(),
        layer.into(),
        (p.0[0] / EPS).round() as i64,
        (p.0[1] / EPS).round() as i64,
    )
}
fn node_index(
    nodes: &mut BTreeMap<(String, String, i64, i64), usize>,
    net: &str,
    layer: &str,
    p: Point,
) -> usize {
    let n = nodes.len();
    *nodes.entry(key(net, layer, p)).or_insert(n)
}
fn add_edge(
    edges: &mut Vec<Edge>,
    widths: &mut BTreeMap<String, f64>,
    kinds: &mut BTreeMap<String, String>,
    id: String,
    net: &str,
    geometry: (usize, usize, f64, &str),
) {
    let (from, to, width, kind) = geometry;
    if from == to || widths.contains_key(&id) {
        return;
    }
    edges.push(Edge {
        id: id.clone(),
        net: net.into(),
        from,
        to,
    });
    widths.insert(id.clone(), width);
    kinds.insert(id, kind.into());
}

/// Construct a graph from native trace, via, pad and filled-zone geometry.
pub fn build(native: &UnitNativeEvidence) -> Result<BoundGraph, String> {
    build_contacts(native, &[])
}

#[derive(Clone)]
struct Contact {
    id: String,
    net: String,
    layer: String,
    terminal: Point,
    witness: Point,
}

fn build_contacts(native: &UnitNativeEvidence, contacts: &[Contact]) -> Result<BoundGraph, String> {
    if native.traces.is_empty() && native.vias.is_empty() {
        return Err("native PFC evidence has no copper traces or vias".into());
    }
    for trace in &native.traces {
        if trace.id.trim().is_empty() || trace.net.trim().is_empty() || trace.points_mm.len() < 2 {
            return Err(format!("invalid native trace {}", trace.id));
        }
    }
    let enabled: std::collections::BTreeSet<&str> = native
        .traces
        .iter()
        .map(|t| t.layer.as_str())
        .chain(
            native
                .vias
                .iter()
                .flat_map(|v| [v.from_layer.as_str(), v.to_layer.as_str()]),
        )
        .chain(native.zones.iter().map(|z| z.layer.as_str()))
        .collect();
    let mut pads = Vec::new();
    for component in &native.components {
        for pad in &component.footprint_pads {
            // Mechanical NPTH mounting holes are represented as pads with no
            // number and no net. They are board geometry, not terminals.
            if pad.net.trim().is_empty() {
                if pad.pad.trim().is_empty() {
                    continue;
                }
                return Err(format!("unknown net at {}.{}", component.id, pad.pad));
            }
            let layers: Vec<_> = pad
                .layers
                .iter()
                .filter(|l| copper(l) && enabled.contains(l.as_str()))
                .cloned()
                .collect();
            if layers.is_empty() {
                continue;
            }
            pads.push((
                format!("{}.{}", component.id, pad.pad),
                pad.net.clone(),
                Point(pad.position_mm),
                layers,
                pad.drill_mm,
                pad.size_mm,
            ));
        }
    }
    let mut candidates: Vec<(String, String, Point)> = Vec::new();
    for trace in &native.traces {
        for p in &trace.points_mm {
            candidates.push((trace.net.clone(), trace.layer.clone(), Point(*p)));
        }
    }
    for (_, net, p, layers, _, _) in &pads {
        for layer in layers {
            candidates.push((net.clone(), layer.clone(), *p));
        }
    }
    for via in &native.vias {
        candidates.push((
            via.net.clone(),
            via.from_layer.clone(),
            Point(via.position_mm),
        ));
        candidates.push((
            via.net.clone(),
            via.to_layer.clone(),
            Point(via.position_mm),
        ));
    }
    for c in contacts {
        candidates.push((c.net.clone(), c.layer.clone(), c.witness));
    }
    // Add trace crossings and T-junctions before splitting any segment.
    for a in 0..native.traces.len() {
        for b in a..native.traces.len() {
            if native.traces[a].net != native.traces[b].net {
                continue;
            }
            if native.traces[a].layer != native.traces[b].layer {
                continue;
            }
            for aw in native.traces[a].points_mm.windows(2) {
                for bw in native.traces[b].points_mm.windows(2) {
                    if let Some(p) =
                        intersection(Point(aw[0]), Point(aw[1]), Point(bw[0]), Point(bw[1]))
                    {
                        candidates.push((
                            native.traces[a].net.clone(),
                            native.traces[a].layer.clone(),
                            p,
                        ));
                    }
                }
            }
        }
    }
    let mut nodes = BTreeMap::<(String, String, i64, i64), usize>::new();
    let mut edges = Vec::new();
    let mut widths = BTreeMap::new();
    let mut kinds = BTreeMap::new();
    for trace in &native.traces {
        for (seg, window) in trace.points_mm.windows(2).enumerate() {
            let a = Point(window[0]);
            let b = Point(window[1]);
            let mut cuts = vec![(0.0, a), (1.0, b)];
            for (net, layer, p) in &candidates {
                if net == &trace.net && layer == &trace.layer {
                    if let Some(t) = point_on(a, b, *p) {
                        cuts.push((t, *p));
                    }
                }
            }
            cuts.sort_by(|x, y| x.0.total_cmp(&y.0));
            cuts.dedup_by(|x, y| (x.0 - y.0).abs() <= EPS);
            for (part, pair) in cuts.windows(2).enumerate() {
                let from = node_index(&mut nodes, &trace.net, &trace.layer, pair[0].1);
                let to = node_index(&mut nodes, &trace.net, &trace.layer, pair[1].1);
                add_edge(
                    &mut edges,
                    &mut widths,
                    &mut kinds,
                    format!("{}:{}", trace.id, seg * 10000 + part),
                    &trace.net,
                    (from, to, trace.width_mm, "trace"),
                );
            }
        }
    }
    for via in &native.vias {
        if via.net.trim().is_empty() {
            return Err(format!("via {} has unknown net", via.id));
        }
        let p = Point(via.position_mm);
        let from = node_index(&mut nodes, &via.net, &via.from_layer, p);
        let to = node_index(&mut nodes, &via.net, &via.to_layer, p);
        add_edge(
            &mut edges,
            &mut widths,
            &mut kinds,
            format!("via:{}", via.id),
            &via.net,
            (from, to, via.diameter_mm, "via"),
        );
    }
    for c in contacts {
        let from = node_index(&mut nodes, &c.net, &c.layer, c.terminal);
        let to = node_index(&mut nodes, &c.net, &c.layer, c.witness);
        add_edge(
            &mut edges,
            &mut widths,
            &mut kinds,
            c.id.clone(),
            &c.net,
            (from, to, 0., "native-pad-contact"),
        );
    }
    let mut terminal_nodes = BTreeMap::new();
    let mut gaps = Vec::new();
    let mut uncertified_nets = std::collections::BTreeSet::new();
    // Side contacts can create parallel copper without a centerline junction.
    // Report affected nets; do not manufacture an exact current from a tree.
    let spans = side_contact_spans(&native.traces);
    for (i, a) in spans.iter().enumerate() {
        for b in &spans[i + 1..] {
            if a.net != b.net || a.layer != b.layer {
                continue;
            }
            for aw in a.points_mm.windows(2) {
                for bw in b.points_mm.windows(2) {
                    let (a0, a1, b0, b1) = (Point(aw[0]), Point(aw[1]), Point(bw[0]), Point(bw[1]));
                    if intersection(a0, a1, b0, b1).is_some()
                        || [a0, a1].iter().any(|p| point_on(b0, b1, *p).is_some())
                        || [b0, b1].iter().any(|p| point_on(a0, a1, *p).is_some())
                    {
                        continue;
                    }
                    let distance = point_segment_distance(a0, a1, b0)
                        .min(point_segment_distance(a0, a1, b1))
                        .min(point_segment_distance(b0, b1, a0))
                        .min(point_segment_distance(b0, b1, a1));
                    if distance <= (a.width_mm + b.width_mm) / 2. + EPS {
                        uncertified_nets.insert(a.net.clone());
                        gaps.push(format!(
                            "{}: finite-width contact {} / {} lacks resolved copper-area sharing",
                            a.net, a.id, b.id
                        ));
                    }
                }
            }
        }
    }
    for (name, net, p, layers, drill, size) in pads {
        let first = node_index(&mut nodes, &net, &layers[0], p);
        if let Some(previous) = terminal_nodes.insert(name.clone(), first) {
            add_edge(
                &mut edges,
                &mut widths,
                &mut kinds,
                format!("package:{name}:{first}"),
                &net,
                (previous, first, 0., "package-pin"),
            );
        }
        if drill[0] > 0.0 || drill[1] > 0.0 {
            for layer in layers.iter().skip(1) {
                let n = node_index(&mut nodes, &net, layer, p);
                add_edge(
                    &mut edges,
                    &mut widths,
                    &mut kinds,
                    format!("pad:{}:{}:{}", name, layer, first),
                    &net,
                    (first, n, 0.0, "pth-pad"),
                );
            }
        }
        let centre_hit = native.traces.iter().any(|t| {
            t.net == net
                && layers.contains(&t.layer)
                && t.points_mm
                    .windows(2)
                    .any(|w| point_on(Point(w[0]), Point(w[1]), p).is_some())
        });
        if !centre_hit
            && !contacts
                .iter()
                .any(|c| c.net == net && c.terminal.dist2(p) < EPS * EPS)
        {
            let radius = 0.5 * size[0].max(size[1]);
            uncertified_nets.insert(net.clone());
            let side_hit = native.traces.iter().any(|t| {
                t.net == net
                    && layers.contains(&t.layer)
                    && t.points_mm.windows(2).any(|w| {
                        point_segment_distance(Point(w[0]), Point(w[1]), p)
                            <= radius + t.width_mm / 2.0 + EPS
                    })
            });
            gaps.push(if side_hit {
                format!("terminal {name} on {net} has possible unsupported side/width-only contact; centreline binding is unsupported")
            } else {
                format!("terminal {name} on {net} has no centreline copper hit")
            });
        }
    }
    // Filled zones are explicit conductors.  Holes are excluded by point-in-polygon.
    for zone in &native.zones {
        for (polygon, poly) in zone.filled_polygons.iter().enumerate() {
            let inside = |p: Point| {
                polygon_contains(&poly.outer_mm, p)
                    && !poly.holes_mm.iter().any(|h| polygon_contains(h, p))
            };
            let targets: Vec<_> = nodes
                .iter()
                .filter_map(|((net, layer, x, y), &n)| {
                    (net == &zone.net
                        && layer == &zone.layer
                        && inside(Point([*x as f64 * EPS, *y as f64 * EPS])))
                    .then_some(n)
                })
                .collect();
            let zn = node_index(&mut nodes, &zone.net, &zone.layer, Point(poly.outer_mm[0]));
            for target in targets {
                add_edge(
                    &mut edges,
                    &mut widths,
                    &mut kinds,
                    format!("zone:{}:{}:{}:{}", zone.id, &zone.layer, polygon, target),
                    &zone.net,
                    (zn, target, 0.0, "zone"),
                );
            }
        }
    }
    // Compare only the explicitly modeled high-power population. This keeps
    // unrelated low-current board clusters from affecting the PFC certificate.
    let mut parent: Vec<usize> = (0..nodes.len()).collect();
    fn root(parent: &mut [usize], mut n: usize) -> usize {
        while parent[n] != n {
            parent[n] = parent[parent[n]];
            n = parent[n];
        }
        n
    }
    for edge in &edges {
        let a = root(&mut parent, edge.from);
        let b = root(&mut parent, edge.to);
        if a != b {
            parent[a] = b;
        }
    }
    for cluster in &native.connectivity_clusters {
        if !cluster.nodes.iter().any(|name| {
            MODELED_COMPONENTS
                .iter()
                .any(|component| name.starts_with(&format!("{component}.")))
        }) {
            continue;
        }
        let members: Vec<_> = cluster
            .nodes
            .iter()
            .filter_map(|name| terminal_nodes.get(name).copied())
            .collect();
        if members.len() != cluster.nodes.len() {
            uncertified_nets.insert(cluster.net.clone());
            gaps.push(format!(
                "native connectivity cluster on {} contains an unbound terminal",
                cluster.net
            ));
        } else if let Some(&first) = members.first() {
            let first_root = root(&mut parent, first);
            if members.iter().any(|n| root(&mut parent, *n) != first_root) {
                uncertified_nets.insert(cluster.net.clone());
                gaps.push(format!(
                    "native connectivity cluster on {} is split in bound copper graph",
                    cluster.net
                ));
            }
        }
    }
    Ok(BoundGraph {
        graph: Graph {
            node_count: nodes.len(),
            edges,
        },
        terminal_nodes,
        edge_width_mm: widths,
        edge_kind: kinds,
        coverage_gaps: gaps,
        uncertified_nets,
    })
}

fn point_in_polygon(poly: &[[f64; 2]], p: Point) -> bool {
    if poly.iter().any(|v| Point(*v).dist2(p) <= EPS * EPS) {
        return true;
    }
    let mut inside = false;
    for (a, b) in poly
        .iter()
        .zip(poly.iter().cycle().skip(1))
        .take(poly.len())
    {
        if ((a[1] > p.0[1]) != (b[1] > p.0[1]))
            && p.0[0] < (b[0] - a[0]) * (p.0[1] - a[1]) / (b[1] - a[1]) + a[0]
        {
            inside = !inside;
        }
    }
    inside
}

/// Connect actual native pad copper to traces/zones. Identity is UUID-based;
/// contact links represent a conductor, never a fabricated trace or width.
pub fn build_with_manufacturing(
    native: &UnitNativeEvidence,
    raw: &serde_json::Value,
    receipt: &serde_json::Value,
) -> Result<BoundGraph, String> {
    use zapote_drc::{manufacturing::Polygon, power_contact};
    let mut contacts = Vec::new();
    let rows = receipt["input"]["pads"]
        .as_array()
        .ok_or("missing native pad copper")?;
    for row in rows {
        let id = row["id"].as_str().ok_or("missing native pad ID")?;
        let Some((prefix, tail)) = id.split_once('@') else {
            return Err("missing native pad layer".into());
        };
        let layer = tail.split(':').next().ok_or("missing native layer")?;
        let target = if let Some((physical, uuid)) = prefix.split_once(':') {
            let (reference, pin) = physical
                .split_once('.')
                .ok_or("missing native physical pin")?;
            let component = raw["reference_to_instance"][reference]
                .as_str()
                .ok_or("missing physical reference binding")?;
            let observed = raw["components"]
                .as_array()
                .ok_or("missing native components")?
                .iter()
                .find(|c| c["id"] == component)
                .ok_or("missing native component")?;
            let pad = observed["footprint_pads"]
                .as_array()
                .ok_or("missing native pads")?
                .iter()
                .find(|p| p["uuid"] == uuid && p["pad"] == pin)
                .ok_or_else(|| format!("pad UUID identity mismatch {id}"))?;
            let position: [f64; 2] =
                serde_json::from_value(pad["position_mm"].clone()).map_err(|e| e.to_string())?;
            native
                .components
                .iter()
                .find(|c| c.id == component)
                .and_then(|c| {
                    c.footprint_pads.iter().find(|p| {
                        p.pad == pin
                            && p.position_mm == position
                            && p.layers.iter().any(|l| l == layer)
                    })
                })
                .map(|p| (p.net.clone(), Point(position)))
        } else {
            native
                .vias
                .iter()
                .find(|v| v.id == prefix && (v.from_layer == layer || v.to_layer == layer))
                .map(|v| (v.net.clone(), Point(v.position_mm)))
        };
        let Some((net, terminal)) = target else {
            continue;
        };
        let polygons: Vec<Polygon> =
            serde_json::from_value(row["inner_copper_polygons"].clone())
                .map_err(|e| format!("{id}: missing native inside copper: {e}"))?;
        let drill: Option<Polygon> =
            serde_json::from_value(row["drill_polygon"].clone()).map_err(|e| e.to_string())?;
        if polygons.len() != 1 {
            return Err(format!(
                "{id}: disconnected/multiple pad copper regions need explicit connectivity"
            ));
        }
        for trace in native
            .traces
            .iter()
            .filter(|t| t.net == net && t.layer == layer)
        {
            for (segment, w) in trace.points_mm.windows(2).enumerate() {
                for (direction, (a, b)) in [(w[0], w[1]), (w[1], w[0])].into_iter().enumerate() {
                    let proof =
                        power_contact::entry(&polygons, drill.as_ref(), a, b, trace.width_mm)?;
                    if let Some(witness) = proof.witness_centerline_mm {
                        contacts.push(Contact {
                            id: format!("contact:{id}:{}:{segment}:{direction}", trace.id),
                            net: net.clone(),
                            layer: layer.into(),
                            terminal,
                            witness: Point(witness),
                        });
                    }
                }
            }
        }
        for zone in native
            .zones
            .iter()
            .filter(|z| z.net == net && z.layer == layer)
        {
            for (index, poly) in zone.filled_polygons.iter().enumerate() {
                if let Some(&witness) = polygons[0].vertices_mm.iter().find(|&&p| {
                    point_in_polygon(&poly.outer_mm, Point(p))
                        && !poly.holes_mm.iter().any(|h| point_in_polygon(h, Point(p)))
                        && !drill
                            .as_ref()
                            .is_some_and(|h| point_in_polygon(&h.vertices_mm, Point(p)))
                }) {
                    contacts.push(Contact {
                        id: format!("contact:{id}:zone:{}:{index}", zone.id),
                        net: net.clone(),
                        layer: layer.into(),
                        terminal,
                        witness: Point(witness),
                    });
                }
            }
        }
    }
    build_contacts(native, &contacts)
}

fn polygon_contains(poly: &[[f64; 2]], p: Point) -> bool {
    if poly.len() < 3 {
        return false;
    }
    let mut inside = false;
    for (a, b) in poly
        .iter()
        .zip(poly.iter().cycle().skip(1))
        .take(poly.len())
    {
        if ((a[1] > p.0[1]) != (b[1] > p.0[1]))
            && p.0[0] < (b[0] - a[0]) * (p.0[1] - a[1]) / (b[1] - a[1]) + a[0]
        {
            inside = !inside;
        }
    }
    inside
}

#[cfg(test)]
mod tests {
    use super::*;
    use zapote_core::unit::UnitNativeEvidence;

    fn evidence(value: serde_json::Value) -> UnitNativeEvidence {
        serde_json::from_value(value).expect("valid native fixture")
    }

    #[test]
    fn span_coalescing_keeps_real_side_contacts_and_width_layer_net_boundaries() {
        let trace = |id: &str, points: Vec<[f64; 2]>| zapote_core::Trace {
            id: id.into(),
            net: "N".into(),
            layer: "F.Cu".into(),
            width_mm: 1.,
            points_mm: points,
        };
        let a = trace("a", vec![[0., 0.], [5., 0.]]);
        let b = trace("b", vec![[10., 0.], [5., 0.]]);
        assert_eq!(side_contact_spans(&[a.clone(), b.clone()]).len(), 1);
        for property in ["width", "layer", "net", "gap", "angle"] {
            let mut changed = b.clone();
            match property {
                "width" => changed.width_mm = 0.5,
                "layer" => changed.layer = "B.Cu".into(),
                "net" => changed.net = "OTHER".into(),
                "gap" => changed.points_mm[1] = [5.1, 0.],
                "angle" => changed.points_mm[0] = [10., 1.],
                _ => unreachable!(),
            }
            assert_eq!(
                side_contact_spans(&[a.clone(), changed]).len(),
                2,
                "{property}"
            );
        }
        let parallel = trace("parallel", vec![[1., 0.7], [9., 0.7]]);
        let native = evidence(
            serde_json::json!({"board_sha256":"fixture","extractor_sha256":"fixture",
            "components":[],"connections":[],"traces":[a,b,parallel],"vias":[],"zones":[],
            "connectivity_clusters":[],"copper_layer_count":2}),
        );
        assert!(build(&native).unwrap().uncertified_nets.contains("N"));
    }

    #[test]
    fn repeated_package_pin_keeps_each_physical_barrel_and_separate_pin_stays_separate() {
        let mut native = evidence(
            serde_json::json!({"board_sha256":"fixture","extractor_sha256":"fixture","components":[
            {"id":"package","mpn":"m","kind":"x","position_mm":[0,0],"footprint_pads":[
                {"pad":"1","net":"N","position_mm":[0,0],"size_mm":[2,2],"drill_mm":[1,1],"layers":["F.Cu","B.Cu"]},
                {"pad":"1","net":"N","position_mm":[10,0],"size_mm":[2,2],"drill_mm":[1,1],"layers":["F.Cu","B.Cu"]}]},
            {"id":"load","mpn":"m","kind":"x","position_mm":[10,5],"footprint_pads":[{"pad":"1","net":"N","position_mm":[10,5],"size_mm":[2,2],"layers":["B.Cu"]}]}],
            "connections":[],"traces":[{"id":"first","net":"N","points_mm":[[0,0],[0,5]],"layer":"F.Cu","width_mm":1},
            {"id":"second","net":"N","points_mm":[[10,0],[10,5]],"layer":"B.Cu","width_mm":1}],"vias":[],"zones":[],"connectivity_clusters":[],"copper_layer_count":2}),
        );
        let bound = build(&native).unwrap();
        assert_eq!(
            bound
                .edge_kind
                .values()
                .filter(|k| k.as_str() == "pth-pad")
                .count(),
            2
        );
        assert_eq!(
            bound
                .edge_kind
                .values()
                .filter(|k| k.as_str() == "package-pin")
                .count(),
            1
        );
        let mut values = vec![0.; bound.graph.node_count];
        values[bound.terminal_nodes["package.1"]] = 1.;
        values[bound.terminal_nodes["load.1"]] = -1.;
        assert!(
            zapote_drc::power_branches::analyze(
                &bound.graph,
                &[zapote_drc::power_branches::Sample {
                    weight: 1.,
                    injections_a: values
                }]
            )
            .is_ok()
        );
        native.components[0].footprint_pads[1].pad = "2".into();
        let bound = build(&native).unwrap();
        assert!(!bound.edge_kind.values().any(|k| k == "package-pin"));
        let mut values = vec![0.; bound.graph.node_count];
        values[bound.terminal_nodes["package.1"]] = 1.;
        values[bound.terminal_nodes["load.1"]] = -1.;
        assert!(
            zapote_drc::power_branches::analyze(
                &bound.graph,
                &[zapote_drc::power_branches::Sample {
                    weight: 1.,
                    injections_a: values
                }]
            )
            .is_err()
        );
    }

    #[test]
    fn native11_binds_nonempty_graph_and_terminals() {
        let raw = include_str!("../../../power-entry/evidence/native-11.json");
        let native: UnitNativeEvidence = serde_json::from_str(raw).unwrap();
        let bound = build(&native).unwrap();
        assert!(bound.graph.edges.len() > native.traces.len());
        assert!(bound.terminal_nodes.len() > 20);
        assert!(
            bound
                .edge_width_mm
                .keys()
                .all(|id| bound.edge_kind.contains_key(id))
        );
        let zone_ids: Vec<_> = bound
            .graph
            .edges
            .iter()
            .filter(|edge| edge.id.starts_with("zone:"))
            .map(|edge| edge.id.as_str())
            .collect();
        let unique: std::collections::BTreeSet<_> = zone_ids.iter().copied().collect();
        assert_eq!(zone_ids.len(), unique.len());
        assert!(
            bound
                .coverage_gaps
                .iter()
                .any(|gap| gap.contains("PFC_BUS_MINUS is split"))
        );
    }

    #[test]
    fn t_branch_is_split_at_junction() {
        let native = evidence(serde_json::json!({
            "board_sha256":"x", "extractor_sha256":"x", "copper_layer_count":2,
            "components":[
                {"id":"source","mpn":"m","kind":"x","position_mm":[0,0],"footprint_pads":[{"pad":"1","net":"PFC_BUS_PLUS","position_mm":[0,0],"size_mm":[1,1],"layers":["F.Cu"]}]},
                {"id":"left","mpn":"m","kind":"x","position_mm":[10,0],"footprint_pads":[{"pad":"1","net":"PFC_BUS_PLUS","position_mm":[10,0],"size_mm":[1,1],"layers":["F.Cu"]}]},
                {"id":"right","mpn":"m","kind":"x","position_mm":[5,5],"footprint_pads":[{"pad":"1","net":"PFC_BUS_PLUS","position_mm":[5,5],"size_mm":[1,1],"layers":["F.Cu"]}]}
            ], "connections":[], "connectivity_clusters":[],
            "traces":[
                {"id":"trunk","net":"PFC_BUS_PLUS","points_mm":[[0,0],[10,0]],"layer":"F.Cu","width_mm":1},
                {"id":"spur","net":"PFC_BUS_PLUS","points_mm":[[5,5],[5,0]],"layer":"F.Cu","width_mm":0.5}
            ], "vias":[], "zones":[]
        }));
        let bound = build(&native).unwrap();
        assert!(
            bound
                .graph
                .edges
                .iter()
                .filter(|e| e.id.starts_with("trunk:"))
                .count()
                >= 2
        );
        assert!(bound.graph.edges.iter().any(|e| e.id.starts_with("spur:")));
    }

    #[test]
    fn unknown_terminal_net_is_an_adapter_error() {
        let native = evidence(serde_json::json!({
            "board_sha256":"x", "extractor_sha256":"x", "copper_layer_count":2,
            "components":[{"id":"bad","mpn":"m","kind":"x","position_mm":[0,0],"footprint_pads":[{"pad":"1","net":"","position_mm":[0,0],"size_mm":[1,1],"layers":["F.Cu"]}]}],
            "connections":[], "connectivity_clusters":[], "traces":[{"id":"t","net":"X","points_mm":[[0,0],[1,0]],"layer":"F.Cu","width_mm":1}], "vias":[], "zones":[]
        }));
        assert!(build(&native).unwrap_err().contains("unknown net"));
    }
}
