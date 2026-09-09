//! Engineering layout checks derived from native KiCad measurements.
//!
//! Connectivity is reconstructed from track endpoints and pad locations.  The
//! `buck.connectivity` census is deliberately not used for electrical truth:
//! it is useful evidence, but accepting it would turn a proximity mistake into
//! a passing return path.
use anyhow::{ensure, Context, Result};
use serde_json::{json, Value};
use std::cmp::Ordering;

#[derive(Clone)]
struct Pad {
    id: String,
    net: String,
    p: [f64; 2],
    layer: String,
}
#[derive(Clone)]
struct Track {
    id: String,
    kind: String,
    net: String,
    layer: String,
    a: [f64; 2],
    b: [f64; 2],
    width: f64,
}

fn dist(a: [f64; 2], b: [f64; 2]) -> f64 {
    (a[0] - b[0]).hypot(a[1] - b[1])
}
fn point_segment(p: [f64; 2], a: [f64; 2], b: [f64; 2]) -> f64 {
    let (dx, dy) = (b[0] - a[0], b[1] - a[1]);
    let l = dx * dx + dy * dy;
    if l == 0.0 {
        return dist(p, a);
    }
    let t = ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / l;
    dist(
        p,
        [a[0] + t.clamp(0.0, 1.0) * dx, a[1] + t.clamp(0.0, 1.0) * dy],
    )
}
fn segment_gap(a: [f64; 2], b: [f64; 2], c: [f64; 2], d: [f64; 2]) -> f64 {
    let cross = |u: [f64; 2], v: [f64; 2]| u[0] * v[1] - u[1] * v[0];
    let ab = [b[0] - a[0], b[1] - a[1]];
    let cd = [d[0] - c[0], d[1] - c[1]];
    let ac = [c[0] - a[0], c[1] - a[1]];
    let denom = cross(ab, cd);
    if denom.abs() > 1e-12 {
        let t = cross(ac, cd) / denom;
        let u = cross(ac, ab) / denom;
        if (0.0..=1.0).contains(&t) && (0.0..=1.0).contains(&u) {
            return 0.0;
        }
    }
    point_segment(a, c, d)
        .min(point_segment(b, c, d))
        .min(point_segment(c, a, b))
        .min(point_segment(d, a, b))
}

fn path_length(
    pads: &[Pad],
    tracks: &[Track],
    from: &str,
    to: &str,
    net: &str,
    tol: f64,
) -> Option<f64> {
    let wanted: Vec<&Pad> = pads.iter().filter(|p| p.id == from || p.id == to).collect();
    if wanted.len() != 2 || wanted.iter().any(|p| p.net != net) {
        return None;
    }
    let ts: Vec<&Track> = tracks
        .iter()
        .filter(|t| t.net == net && t.kind == "segment")
        .collect();
    // Split centerlines at real same-layer crossings, T-junctions, pads and vias.
    let mut splits: Vec<Vec<[f64; 2]>> = ts.iter().map(|t| vec![t.a, t.b]).collect();
    let cross = |a: [f64; 2], b: [f64; 2]| a[0] * b[1] - a[1] * b[0];
    for (i, t) in ts.iter().enumerate() {
        for other in &ts {
            if t.layer != other.layer {
                continue;
            }
            for point in [other.a, other.b] {
                if point_segment(point, t.a, t.b) <= tol {
                    splits[i].push(point);
                }
            }
            let u = [t.b[0] - t.a[0], t.b[1] - t.a[1]];
            let v = [other.b[0] - other.a[0], other.b[1] - other.a[1]];
            let offset = [other.a[0] - t.a[0], other.a[1] - t.a[1]];
            let denominator = cross(u, v);
            if denominator.abs() > 1e-12 {
                let along = cross(offset, v) / denominator;
                let across = cross(offset, u) / denominator;
                if (0.0..=1.0).contains(&along) && (0.0..=1.0).contains(&across) {
                    splits[i].push([t.a[0] + along * u[0], t.a[1] + along * u[1]]);
                }
            }
        }
        for p in &wanted {
            if p.layer == t.layer && point_segment(p.p, t.a, t.b) <= tol {
                splits[i].push(p.p);
            }
        }
        for v in tracks
            .iter()
            .filter(|v| v.net == net && v.kind == "via" && v.layer == "F.Cu-B.Cu")
        {
            if point_segment(v.a, t.a, t.b) <= tol {
                splits[i].push(v.a);
            }
        }
        splits[i].sort_by(|a, b| dist(*a, t.a).total_cmp(&dist(*b, t.a)));
        splits[i].dedup_by(|a, b| dist(*a, *b) <= tol);
    }
    let mut nodes: Vec<([f64; 2], String)> = Vec::new();
    let mut line_edges = Vec::new();
    for (t, points) in ts.iter().zip(splits) {
        let offset = nodes.len();
        for (j, p) in points.iter().enumerate() {
            nodes.push((*p, t.layer.clone()));
            if j > 0 {
                line_edges.push((offset + j - 1, offset + j, dist(points[j - 1], *p)));
            }
        }
    }
    let start = nodes.len();
    let goal = start + 1;
    nodes.extend(wanted.iter().map(|p| (p.p, p.layer.clone())));
    let mut edges = vec![Vec::<(usize, f64)>::new(); nodes.len()];
    for (a, b, w) in line_edges {
        edges[a].push((b, w));
        edges[b].push((a, w));
    }
    for (i, (point, layer)) in nodes.iter().enumerate() {
        for (j, (other, other_layer)) in nodes.iter().enumerate().skip(i + 1) {
            if dist(*point, *other) > tol {
                continue;
            }
            let via = tracks.iter().any(|v| {
                v.kind == "via"
                    && v.net == net
                    && v.layer == "F.Cu-B.Cu"
                    && dist(v.a, *point) <= tol
            });
            if layer == other_layer || via {
                edges[i].push((j, 0.0));
                edges[j].push((i, 0.0));
            }
        }
    }
    let mut d = vec![f64::INFINITY; nodes.len()];
    d[start] = 0.0;
    let mut used = vec![false; nodes.len()];
    for _ in 0..nodes.len() {
        let u = (0..nodes.len())
            .filter(|&i| !used[i])
            .min_by(|&a, &b| d[a].partial_cmp(&d[b]).unwrap_or(Ordering::Equal));
        let Some(u) = u else { break };
        used[u] = true;
        for &(v, w) in &edges[u] {
            d[v] = d[v].min(d[u] + w);
        }
    }
    d[goal].is_finite().then_some(d[goal])
}

/// Evaluate the `engineering-layout` payload emitted by `layout_native`.
pub fn evaluate(input: Value) -> Result<Value> {
    ensure!(
        input.get("profile").and_then(Value::as_str) == Some("engineering-layout"),
        "engineering-layout profile required"
    );
    let m = input
        .get("measurement")
        .context("native measurement missing")?;
    let c: Value = serde_json::from_str(include_str!("../engineering/layout-contract.json"))
        .context("embedded layout contract is invalid")?;
    let mut findings = Vec::new();
    let mut pads = Vec::new();
    for fp in m
        .get("footprints")
        .and_then(Value::as_array)
        .context("footprint census missing")?
    {
        let r = fp
            .get("reference")
            .and_then(Value::as_str)
            .context("footprint reference missing")?;
        for p in fp
            .get("pads")
            .and_then(Value::as_array)
            .context("pad census missing")?
        {
            let n = p
                .get("number")
                .and_then(Value::as_str)
                .context("pad number missing")?;
            let pos = p
                .get("position_mm")
                .or_else(|| p.get("pos_mm"))
                .and_then(Value::as_array)
                .context("pad position missing")?;
            ensure!(pos.len() == 2, "pad position must have two coordinates");
            pads.push(Pad {
                id: format!("{r}.{n}"),
                net: p
                    .get("net")
                    .and_then(Value::as_str)
                    .unwrap_or("")
                    .to_owned(),
                p: [
                    pos[0].as_f64().context("invalid x")?,
                    pos[1].as_f64().context("invalid y")?,
                ],
                layer: p
                    .get("layer")
                    .and_then(Value::as_str)
                    .unwrap_or("F.Cu")
                    .to_owned(),
            });
        }
    }
    let mut tracks = Vec::new();
    let mut unsupported = false;
    for t in m
        .get("buck")
        .and_then(|v| v.get("tracks").or_else(|| v.get("copper")))
        .and_then(Value::as_array)
        .context("native copper census missing")?
    {
        let kind = t.get("kind").and_then(Value::as_str).unwrap_or("");
        if !["segment", "via"].contains(&kind) {
            unsupported = true;
            continue;
        }
        let a = t
            .get("start_mm")
            .and_then(Value::as_array)
            .context("track start missing")?;
        let b = t
            .get("end_mm")
            .and_then(Value::as_array)
            .context("track end missing")?;
        tracks.push(Track {
            id: t
                .get("uuid")
                .and_then(Value::as_str)
                .unwrap_or("")
                .to_owned(),
            kind: kind.to_owned(),
            net: t
                .get("net")
                .and_then(Value::as_str)
                .unwrap_or("")
                .to_owned(),
            layer: t
                .get("layer")
                .and_then(Value::as_str)
                .unwrap_or("")
                .to_owned(),
            a: [
                a[0].as_f64().context("invalid track x")?,
                a[1].as_f64().context("invalid track y")?,
            ],
            b: [
                b[0].as_f64().context("invalid track x")?,
                b[1].as_f64().context("invalid track y")?,
            ],
            width: t.get("width_mm").and_then(Value::as_f64).unwrap_or(0.0),
        });
    }
    if unsupported {
        findings.push(json!({"id":"unsupported_copper_geometry","message":"arcs, zones, or unmodeled contacts cannot establish layout evidence"}));
    }
    if input
        .get("base_result")
        .and_then(|v| v.get("status"))
        .and_then(Value::as_str)
        != Some("pass")
    {
        findings.push(
            json!({"id":"base_drc_failed","message":"the retained native U1 result must be pass"}),
        );
    }
    let tol = 1e-6;
    let mut copper_paths = serde_json::Map::new();
    for (from, to, net, key) in [
        ("C9.2", "U3.1", "gnd", "ground_return"),
        ("C9.1", "U3.3", "+15V", "input_path"),
    ] {
        match path_length(&pads, &tracks, from, to, net, tol) {
            Some(length) => {
                copper_paths.insert(
                    key.to_owned(),
                    json!({"from":from,"to":to,"net":net,"length_mm":length}),
                );
                let limit = c
                    .get("checks")
                    .and_then(|v| v.get("path_max_mm"))
                    .and_then(Value::as_f64)
                    .unwrap_or(60.0);
                if length > limit {
                    findings.push(json!({"id":key,"path_length_mm":length,"maximum_mm":limit}));
                }
            }
            None => {
                copper_paths.insert(key.to_owned(), Value::Null);
                findings.push(json!({"id":format!("{key}_indeterminate"),"message":"no connected copper path from native endpoints"}));
            }
        }
    }
    let min_power = c
        .get("checks")
        .and_then(|v| v.get("min_power_width_mm"))
        .and_then(Value::as_f64)
        .unwrap_or(0.5);
    for t in tracks
        .iter()
        .filter(|t| ["+15V", "+3V3", "sw", "gnd"].contains(&t.net.as_str()) && t.kind == "segment")
    {
        if t.width < min_power {
            findings.push(json!({"id":"power_neckdown","track":t.id,"width_mm":t.width,"minimum_mm":min_power}));
        }
    }
    let fb_min = c
        .get("checks")
        .and_then(|v| v.get("fb_sw_separation_min_mm"))
        .and_then(Value::as_f64)
        .unwrap_or(1.0);
    for f in tracks
        .iter()
        .filter(|t| t.net == "fb" && t.kind == "segment")
    {
        for s in tracks
            .iter()
            .filter(|t| t.net == "sw" && t.kind == "segment" && t.layer == f.layer)
        {
            let gap = (segment_gap(f.a, f.b, s.a, s.b) - (f.width + s.width) * 0.5).max(0.0);
            if gap < fb_min {
                findings.push(json!({"id":"fb_sw_separation","distance_mm":gap}));
            }
        }
    }
    let presentation = input
        .get("presentation")
        .context("native presentation missing")?;
    let labels = presentation["labels"]
        .as_array()
        .context("native labels missing")?;
    let mut presentation_findings = Vec::new();
    for (i, label) in labels.iter().enumerate() {
        let rect = |v: &Value| -> Result<[f64; 4]> {
            let a = v["bounds_mm"].as_array().context("label bounds missing")?;
            ensure!(a.len() == 4, "invalid label bounds");
            Ok([
                a[0].as_f64().context("x")?,
                a[1].as_f64().context("y")?,
                a[2].as_f64().context("x")?,
                a[3].as_f64().context("y")?,
            ])
        };
        let a = rect(label)?;
        if label["height_mm"].as_f64().is_none_or(|v| v < 0.8) {
            presentation_findings.push(json!({"id":"label_unreadable","label":label["text"]}));
        }
        for other in labels.iter().skip(i + 1) {
            let b = rect(other)?;
            if label["layer"] == other["layer"]
                && a[0] < b[2]
                && b[0] < a[2]
                && a[1] < b[3]
                && b[1] < a[3]
            {
                presentation_findings
                    .push(json!({"id":"label_overlap","labels":[label["text"],other["text"]]}));
            }
        }
    }
    if labels.is_empty() {
        presentation_findings.push(json!({"id":"labels_missing"}));
    }
    let electrical = if unsupported
        || findings
            .iter()
            .any(|f| f["id"].as_str().unwrap_or("").contains("indeterminate"))
    {
        "indeterminate"
    } else if findings.is_empty() {
        "pass"
    } else {
        "fail"
    };
    let presentation_status = if presentation_findings.is_empty() {
        "pass"
    } else {
        "fail"
    };
    findings.extend(presentation_findings);
    let overall = if electrical == "indeterminate" {
        "indeterminate"
    } else if electrical == "pass" && presentation_status == "pass" {
        "pass"
    } else {
        "fail"
    };
    Ok(
        json!({"schema_version":"engineering-layout/v1","profile":"engineering-layout","status":overall,"layout":{"status":overall,"electrical":electrical,"presentation":presentation_status},"measurements":{"copper_path_mm":copper_paths,"power_bottleneck_width_mm":tracks.iter().filter(|t|["+15V","+3V3","gnd","sw"].contains(&t.net.as_str())&&t.kind=="segment").map(|t|t.width).fold(f64::INFINITY,f64::min)},"findings":findings,"presentation_observations":presentation,"hardware_validated":false}),
    )
}
