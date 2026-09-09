//! Nine-component buck acceptance policy. KiCad owns geometry and connectivity.
use anyhow::{ensure, Context, Result};
use serde::Deserialize;
use serde_json::{json, Value};
use std::collections::{BTreeMap, BTreeSet};

#[derive(Deserialize)]
struct Pad {
    number: String,
    net: String,
    position_mm: [f64; 2],
}

#[derive(Deserialize)]
struct Footprint {
    reference: String,
    position_mm: [f64; 2],
    angle_deg: f64,
    bounds_mm: [f64; 4],
    pads: Vec<Pad>,
}

#[derive(Deserialize)]
pub struct Track {
    uuid: String,
    kind: String,
    net: String,
    layer: String,
    width_mm: f64,
    start_mm: [f64; 2],
    end_mm: [f64; 2],
    bounds_mm: [f64; 4],
}

#[derive(Deserialize)]
pub struct Cluster {
    pad: String,
    pads: Vec<String>,
    tracks: Vec<String>,
}

#[derive(Deserialize)]
pub struct BuckMeasurement {
    tracks: Vec<Track>,
    connectivity: Vec<Cluster>,
}

#[derive(Deserialize)]
struct Measurement {
    kicad_version: String,
    board_sha256: String,
    protected_sha256: String,
    footprints: Vec<Footprint>,
    buck: BuckMeasurement,
}

#[derive(Deserialize)]
struct Terminal {
    net: String,
    position_mm: [f64; 2],
}

#[derive(Deserialize)]
struct Checks {
    input_locality_max_mm: f64,
    boot_locality_max_mm: f64,
    output_locality_max_mm: f64,
    fb_locality_max_mm: f64,
    fb_pair_max_mm: f64,
    fb_sw_separation_min_mm: f64,
    ground_return_max_mm: f64,
}

#[derive(Deserialize)]
struct Contract {
    kicad_version: String,
    protected_sha256: String,
    outline_mm: [f64; 4],
    supported_layers: Vec<String>,
    allowed_copper_kinds: Vec<String>,
    min_power_width_mm: f64,
    min_signal_width_mm: f64,
    power_nets: Vec<String>,
    signal_nets: Vec<String>,
    pad_census: BTreeMap<String, usize>,
    net_mapping: BTreeMap<String, String>,
    terminals: BTreeMap<String, Terminal>,
    obligations: BTreeMap<String, Vec<String>>,
    checks: Checks,
}

#[derive(Deserialize)]
struct Drc {
    #[serde(rename = "$schema")]
    schema: String,
    coordinate_units: String,
    source: String,
    kicad_version: String,
    violations: Vec<Value>,
    unconnected_items: Vec<Value>,
    ignored_checks: Vec<Value>,
    included_severities: Vec<String>,
    schematic_parity: Vec<Value>,
}

#[derive(Deserialize)]
pub struct Input {
    measurement: Measurement,
    contract: Contract,
    drc: Drc,
}

fn footprint<'a>(measurement: &'a Measurement, reference: &str) -> Result<&'a Footprint> {
    let mut found = measurement
        .footprints
        .iter()
        .filter(|f| f.reference == reference);
    let fp = found
        .next()
        .with_context(|| format!("missing footprint {reference}"))?;
    ensure!(found.next().is_none(), "duplicate footprint {reference}");
    Ok(fp)
}

fn pad_position(measurement: &Measurement, pad: &str) -> Result<[f64; 2]> {
    let (reference, number) = pad.split_once('.').context("invalid pad identity")?;
    let fp = footprint(measurement, reference)?;
    let mut found = fp.pads.iter().filter(|p| p.number == number);
    let entry = found.next().with_context(|| format!("missing pad {pad}"))?;
    ensure!(found.next().is_none(), "duplicate pad {pad}");
    Ok(entry.position_mm)
}

fn distance(a: [f64; 2], b: [f64; 2]) -> f64 {
    (a[0] - b[0]).hypot(a[1] - b[1])
}

fn is_digest(value: &str) -> bool {
    value.len() == 64 && value.bytes().all(|c| c.is_ascii_hexdigit())
}

fn segment_distance(a: [f64; 2], b: [f64; 2], c: [f64; 2], d: [f64; 2]) -> f64 {
    let ux = b[0] - a[0];
    let uy = b[1] - a[1];
    let vx = d[0] - c[0];
    let vy = d[1] - c[1];
    let denom = ux * vy - uy * vx;
    if denom.abs() > 1e-12 {
        let t = ((c[0] - a[0]) * vy - (c[1] - a[1]) * vx) / denom;
        let u = ((c[0] - a[0]) * uy - (c[1] - a[1]) * ux) / denom;
        if (0.0..=1.0).contains(&t) && (0.0..=1.0).contains(&u) {
            return 0.0;
        }
    }
    let point_segment = |p: [f64; 2], s: [f64; 2], e: [f64; 2]| {
        let dx = e[0] - s[0];
        let dy = e[1] - s[1];
        let len2 = dx * dx + dy * dy;
        if len2 == 0.0 {
            return distance(p, s);
        }
        let t = ((p[0] - s[0]) * dx + (p[1] - s[1]) * dy) / len2;
        let t = t.clamp(0.0, 1.0);
        distance(p, [s[0] + t * dx, s[1] + t * dy])
    };
    point_segment(a, c, d)
        .min(point_segment(b, c, d))
        .min(point_segment(c, a, b))
        .min(point_segment(d, a, b))
}

pub fn evaluate(input: Input) -> Result<Value> {
    let Input {
        measurement: m,
        contract: c,
        drc,
    } = input;
    ensure!(
        m.kicad_version == c.kicad_version && drc.kicad_version == c.kicad_version,
        "unqualified KiCad version"
    );
    ensure!(
        is_digest(&m.board_sha256)
            && is_digest(&m.protected_sha256)
            && is_digest(&c.protected_sha256),
        "invalid content identity"
    );
    ensure!(
        drc.schema == "https://schemas.kicad.org/drc.v1.json"
            && drc.coordinate_units == "mm"
            && drc.source == "candidate.kicad_pcb",
        "unexpected DRC schema, units, or source"
    );
    ensure!(
        drc.included_severities.iter().any(|s| s == "error")
            && drc.included_severities.iter().any(|s| s == "warning")
            && drc.included_severities.iter().any(|s| s == "exclusion"),
        "incomplete DRC severities"
    );
    let allowed_ignored = [
        "missing_courtyard",
        "track_not_centered_on_via",
        "tuning_profile_track_geometries",
        "footprint_filters_mismatch",
        "footprint_type_mismatch",
    ];
    for ignored in &drc.ignored_checks {
        ensure!(
            allowed_ignored.contains(&ignored["key"].as_str().context("invalid ignored check")?),
            "applicable DRC check disabled: {ignored}"
        );
    }
    ensure!(
        c.outline_mm.iter().all(|v| v.is_finite())
            && c.outline_mm[0] < c.outline_mm[2]
            && c.outline_mm[1] < c.outline_mm[3],
        "invalid buck outline"
    );
    for value in [
        c.checks.input_locality_max_mm,
        c.checks.boot_locality_max_mm,
        c.checks.output_locality_max_mm,
        c.checks.fb_locality_max_mm,
        c.checks.fb_pair_max_mm,
        c.checks.fb_sw_separation_min_mm,
        c.checks.ground_return_max_mm,
        c.min_power_width_mm,
        c.min_signal_width_mm,
    ] {
        ensure!(value.is_finite() && value > 0.0, "invalid buck rule");
    }
    let expected_pads: BTreeSet<&str> = c.net_mapping.keys().map(String::as_str).collect();
    ensure!(!expected_pads.is_empty(), "empty buck pad census");
    let mut obligated: BTreeSet<&str> = BTreeSet::new();
    for pads in c.obligations.values() {
        for pad in pads {
            obligated.insert(pad.as_str());
        }
    }
    ensure!(
        obligated == expected_pads,
        "obligations must cover the pad census"
    );
    let mut census: BTreeMap<&str, usize> = BTreeMap::new();
    for pad in expected_pads.iter() {
        let reference = pad.split_once('.').context("invalid pad identity")?.0;
        *census.entry(reference).or_insert(0) += 1;
    }
    ensure!(
        census.keys().copied().collect::<BTreeSet<_>>()
            == c.pad_census
                .keys()
                .map(String::as_str)
                .collect::<BTreeSet<_>>(),
        "unexpected buck footprint census"
    );
    for (reference, count) in &c.pad_census {
        ensure!(
            census.get(reference.as_str()) == Some(count),
            "unexpected pad census for {reference}"
        );
    }
    ensure!(
        m.footprints.len() == c.pad_census.len(),
        "expected exactly the census footprints"
    );
    for fp in &m.footprints {
        ensure!(
            fp.position_mm
                .iter()
                .chain(fp.bounds_mm.iter())
                .chain([&fp.angle_deg])
                .all(|v| v.is_finite()),
            "nonfinite footprint geometry"
        );
        ensure!(
            fp.bounds_mm[0] < fp.bounds_mm[2] && fp.bounds_mm[1] < fp.bounds_mm[3],
            "invalid footprint bounds"
        );
        ensure!(
            fp.pads.len()
                == *c
                    .pad_census
                    .get(&fp.reference)
                    .context("unknown footprint")?,
            "unexpected pad census for {}",
            fp.reference
        );
        for p in &fp.pads {
            ensure!(
                p.position_mm.iter().all(|v| v.is_finite()),
                "nonfinite pad geometry"
            );
            let identity = format!("{}.{}", fp.reference, p.number);
            ensure!(
                c.net_mapping.get(&identity) == Some(&p.net),
                "net_mismatch:{identity}"
            );
        }
    }
    let mut findings = Vec::new();
    if m.protected_sha256 != c.protected_sha256 {
        findings.push(json!({"id": "protected_state_changed"}));
    }
    for (reference, terminal) in &c.terminals {
        let fp = footprint(&m, reference)?;
        ensure!(
            terminal.position_mm.iter().all(|v| v.is_finite()),
            "nonfinite terminal pose"
        );
        if distance(fp.position_mm, terminal.position_mm) > 1e-6 {
            findings.push(json!({"id": format!("terminal_moved:{reference}")}));
        }
        for p in &fp.pads {
            if p.net != terminal.net {
                findings.push(json!({"id": format!("net_mismatch:{reference}.{}", p.number)}));
            }
        }
    }
    for fp in &m.footprints {
        let [left, top, right, bottom] = fp.bounds_mm;
        let [x0, y0, x1, y1] = c.outline_mm;
        if left < x0 || top < y0 || right > x1 || bottom > y1 {
            findings.push(json!({"id": format!("outside_outline:{}", fp.reference)}));
        }
    }
    let clusters: BTreeMap<&str, &Cluster> = m
        .buck
        .connectivity
        .iter()
        .map(|c| (c.pad.as_str(), c))
        .collect();
    ensure!(
        clusters.len() == m.buck.connectivity.len()
            && clusters.keys().copied().collect::<BTreeSet<_>>() == expected_pads,
        "incomplete or duplicate connectivity census"
    );
    let tracks: BTreeMap<&str, &Track> =
        m.buck.tracks.iter().map(|t| (t.uuid.as_str(), t)).collect();
    ensure!(
        tracks.len() == m.buck.tracks.len() && !tracks.contains_key(""),
        "invalid track identities"
    );
    let admitted: BTreeSet<&str> = c
        .power_nets
        .iter()
        .chain(c.signal_nets.iter())
        .map(String::as_str)
        .collect();
    let mut cluster_net: BTreeMap<&str, &str> = BTreeMap::new();
    for cluster in clusters.values() {
        let pads: BTreeSet<&str> = cluster.pads.iter().map(String::as_str).collect();
        let ids: BTreeSet<&str> = cluster.tracks.iter().map(String::as_str).collect();
        ensure!(
            pads.len() == cluster.pads.len()
                && pads.contains(cluster.pad.as_str())
                && pads.is_subset(&expected_pads),
            "invalid connected-pad evidence"
        );
        ensure!(
            ids.len() == cluster.tracks.len() && ids.iter().all(|id| tracks.contains_key(id)),
            "invalid connected-track evidence"
        );
        for pad in &pads {
            let other = clusters
                .get(pad)
                .context("missing reciprocal connectivity")?;
            ensure!(
                other
                    .pads
                    .iter()
                    .map(String::as_str)
                    .collect::<BTreeSet<_>>()
                    == pads
                    && other
                        .tracks
                        .iter()
                        .map(String::as_str)
                        .collect::<BTreeSet<_>>()
                        == ids,
                "inconsistent native clusters"
            );
        }
        let nets: BTreeSet<&str> = pads
            .iter()
            .map(|pad| {
                c.net_mapping
                    .get(*pad)
                    .map(String::as_str)
                    .context("unknown pad")
            })
            .collect::<Result<_>>()?;
        if nets.len() != 1 {
            findings.push(json!({"id": format!("shorted_cluster:{}", cluster.pad)}));
        }
        cluster_net.insert(
            cluster.pad.as_str(),
            *nets.iter().next().context("empty cluster")?,
        );
    }
    for (net, pads) in &c.obligations {
        let first = pads.first().context("empty obligation")?;
        let anchor = clusters
            .get(first.as_str())
            .context("missing obligation cluster")?;
        let members: BTreeSet<&str> = anchor.pads.iter().map(String::as_str).collect();
        let expected: BTreeSet<&str> = pads.iter().map(String::as_str).collect();
        if members != expected {
            for pad in expected.difference(&members) {
                findings.push(json!({"id": format!("unrouted:{pad}:{net}")}));
            }
            for pad in members.difference(&expected) {
                findings.push(json!({"id": format!("unintended_connection:{pad}")}));
            }
        }
        if members == expected && anchor.tracks.is_empty() {
            findings.push(json!({"id": format!("unrouted:{first}:{net}")}));
        }
    }
    for track in tracks.values() {
        ensure!(
            track
                .start_mm
                .iter()
                .chain(track.end_mm.iter())
                .chain(track.bounds_mm.iter())
                .chain([&track.width_mm])
                .all(|v| v.is_finite())
                && track.width_mm > 0.0
                && track.bounds_mm[0] <= track.bounds_mm[2]
                && track.bounds_mm[1] <= track.bounds_mm[3],
            "invalid track geometry"
        );
        let layer_ok = c.supported_layers.contains(&track.layer)
            || (track.kind == "via" && track.layer == "F.Cu-B.Cu");
        if !c.allowed_copper_kinds.contains(&track.kind)
            || !layer_ok
            || !admitted.contains(track.net.as_str())
        {
            findings.push(json!({"id": format!("unsupported_track:{}", track.uuid)}));
            continue;
        }
        if track.kind == "via" && track.layer != "F.Cu-B.Cu" {
            findings.push(json!({"id": format!("unsupported_track:{}", track.uuid)}));
            continue;
        }
        if track.kind == "segment" {
            let minimum = if c.power_nets.contains(&track.net) {
                c.min_power_width_mm
            } else {
                c.min_signal_width_mm
            };
            if track.width_mm < minimum - 1e-9 {
                findings.push(json!({
                    "id": format!("narrow_copper:{}", track.uuid),
                    "width_mm": track.width_mm,
                    "minimum_mm": minimum,
                }));
            }
        }
        let [left, top, right, bottom] = track.bounds_mm;
        let [x0, y0, x1, y1] = c.outline_mm;
        if left < x0 || top < y0 || right > x1 || bottom > y1 {
            findings.push(json!({"id": format!("copper_outside_outline:{}", track.uuid)}));
        }
        let anchor = clusters
            .values()
            .find(|cluster| cluster.tracks.iter().any(|id| id == &track.uuid));
        let Some(anchor) = anchor else {
            findings.push(json!({"id": format!("extraneous_copper:{}", track.uuid)}));
            continue;
        };
        let member_nets: BTreeSet<&str> = anchor
            .pads
            .iter()
            .map(|pad| c.net_mapping.get(pad.as_str()).map(String::as_str))
            .collect::<Option<_>>()
            .context("unknown pad in cluster")?;
        if !member_nets.contains(track.net.as_str()) {
            findings.push(json!({"id": format!("wrong_net:{}", track.uuid)}));
        }
    }
    let mut locality = |id: &str, a: &str, b: &str, max: f64| -> Result<()> {
        let distance = distance(pad_position(&m, a)?, pad_position(&m, b)?);
        ensure!(distance.is_finite(), "invalid distance measurement");
        if distance > max {
            findings.push(json!({"id": format!("{id}:{a}:{b}"), "distance_mm": distance}));
        }
        Ok(())
    };
    locality(
        "input_locality",
        "C9.1",
        "U3.3",
        c.checks.input_locality_max_mm,
    )?;
    locality(
        "input_locality",
        "C9.2",
        "U3.1",
        c.checks.input_locality_max_mm,
    )?;
    locality(
        "boot_locality",
        "C10.1",
        "U3.6",
        c.checks.boot_locality_max_mm,
    )?;
    locality(
        "boot_locality",
        "C10.2",
        "U3.2",
        c.checks.boot_locality_max_mm,
    )?;
    for output in ["C11.1", "C12.1", "C13.1"] {
        locality(
            "output_locality",
            "L2.2",
            output,
            c.checks.output_locality_max_mm,
        )?;
    }
    locality("fb_locality", "R16.2", "U3.4", c.checks.fb_locality_max_mm)?;
    locality("fb_locality", "R17.1", "U3.4", c.checks.fb_locality_max_mm)?;
    locality("fb_pair", "R16.2", "R17.1", c.checks.fb_pair_max_mm)?;
    let fb_pads = ["U3.4", "R16.2", "R17.1"];
    let sw_pads = ["U3.2", "C10.2", "L2.1"];
    let mut separation = f64::INFINITY;
    for fb in fb_pads {
        for sw in sw_pads {
            separation = separation.min(distance(pad_position(&m, fb)?, pad_position(&m, sw)?));
        }
    }
    for track in tracks.values() {
        if track.kind != "segment" {
            continue;
        }
        let counter = if track.net == "fb" {
            sw_pads.as_slice()
        } else if track.net == "sw" {
            fb_pads.as_slice()
        } else {
            continue;
        };
        for pad in counter {
            let center = pad_position(&m, pad)?;
            let point_segment = |p: [f64; 2]| {
                let dx = track.end_mm[0] - track.start_mm[0];
                let dy = track.end_mm[1] - track.start_mm[1];
                let len2 = dx * dx + dy * dy;
                if len2 == 0.0 {
                    return distance(p, track.start_mm);
                }
                let t = ((p[0] - track.start_mm[0]) * dx + (p[1] - track.start_mm[1]) * dy) / len2;
                let t = t.clamp(0.0, 1.0);
                distance(p, [track.start_mm[0] + t * dx, track.start_mm[1] + t * dy])
            };
            separation = separation.min(point_segment(center));
        }
    }
    let fb_tracks: Vec<&Track> = tracks
        .values()
        .filter(|t| t.kind == "segment" && t.net == "fb")
        .copied()
        .collect();
    let sw_tracks: Vec<&Track> = tracks
        .values()
        .filter(|t| t.kind == "segment" && t.net == "sw")
        .copied()
        .collect();
    for fb in &fb_tracks {
        for sw in &sw_tracks {
            if fb.layer == sw.layer {
                separation = separation.min(segment_distance(
                    fb.start_mm,
                    fb.end_mm,
                    sw.start_mm,
                    sw.end_mm,
                ));
            }
        }
    }
    ensure!(separation.is_finite(), "invalid separation measurement");
    if separation < c.checks.fb_sw_separation_min_mm {
        findings.push(json!({"id": "fb_sw_separation", "distance_mm": separation}));
    }
    let gnd_anchor = clusters
        .values()
        .find(|cluster| cluster_net[cluster.pad.as_str()] == "gnd")
        .context("missing ground cluster")?;
    for pad in ["C9.2", "C11.2", "C12.2", "C13.2"] {
        if !gnd_anchor.pads.iter().any(|p| p == pad) {
            continue;
        }
        let center = pad_position(&m, pad)?;
        let mut nearest = f64::INFINITY;
        for id in &gnd_anchor.tracks {
            let track = tracks.get(id.as_str()).context("missing ground track")?;
            if track.kind == "via" {
                nearest = nearest.min(distance(center, track.start_mm));
            } else {
                let dx = track.end_mm[0] - track.start_mm[0];
                let dy = track.end_mm[1] - track.start_mm[1];
                let len2 = dx * dx + dy * dy;
                let t = if len2 == 0.0 {
                    0.0
                } else {
                    (((center[0] - track.start_mm[0]) * dx + (center[1] - track.start_mm[1]) * dy)
                        / len2)
                        .clamp(0.0, 1.0)
                };
                nearest = nearest.min(distance(
                    center,
                    [track.start_mm[0] + t * dx, track.start_mm[1] + t * dy],
                ));
            }
        }
        ensure!(
            nearest.is_finite() || gnd_anchor.tracks.is_empty(),
            "invalid ground return measurement"
        );
        if nearest > c.checks.ground_return_max_mm {
            findings.push(json!({"id": format!("ground_return:{pad}"), "distance_mm": nearest}));
        }
    }
    for violation in drc.violations.iter().chain(drc.schematic_parity.iter()) {
        let kind = violation["type"]
            .as_str()
            .context("invalid DRC violation")?;
        let items = violation["items"].as_array().context("missing DRC items")?;
        ensure!(!items.is_empty(), "empty DRC item identities");
        let mut identities = items
            .iter()
            .map(|item| item["uuid"].as_str().context("invalid DRC item identity"))
            .collect::<Result<Vec<_>>>()?;
        identities.sort_unstable();
        findings.push(
            json!({"id": format!("kicad:{kind}:{}", identities.join(":")), "evidence": violation}),
        );
    }
    for item in &drc.unconnected_items {
        ensure!(
            item["type"] == "unconnected_items",
            "unexpected open-connection report"
        );
    }
    if !drc.unconnected_items.is_empty() {
        findings.push(json!({"id": "open_connections", "count": drc.unconnected_items.len()}));
    }
    Ok(
        json!({"status": if findings.is_empty() {"pass"} else {"fail"},
        "scope": "buck_3v3", "board_sha256": m.board_sha256,
        "findings": findings,
        "open_connection_evidence": drc.unconnected_items}),
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn partial_digest_is_not_a_content_identity() {
        assert!(!is_digest("0123456789abcdef"));
    }

    #[test]
    fn parallel_tracks_never_touch() {
        let gap = segment_distance([0.0, 0.0], [4.0, 0.0], [0.0, 1.0], [4.0, 1.0]);
        assert!((gap - 1.0).abs() < 1e-9, "unexpected gap {gap}");
    }

    #[test]
    fn crossing_tracks_measure_zero() {
        let gap = segment_distance([0.0, 0.0], [4.0, 4.0], [0.0, 4.0], [4.0, 0.0]);
        assert!(gap < 1e-9, "unexpected gap {gap}");
    }

    #[test]
    fn asymmetric_oracle_probe_uses_kicad_clockwise_rotation() {
        // pcbnew ground truth: local offset (10, 4) at 45 deg lands at
        // (9.899495, -4.242641) under KiCad's clockwise R(-theta).
        let theta = 45.0_f64.to_radians();
        let (dx, dy) = (10.0_f64, 4.0_f64);
        let world = [
            dx * theta.cos() + dy * theta.sin(),
            -dx * theta.sin() + dy * theta.cos(),
        ];
        assert!((world[0] - 9.899_495).abs() < 1e-5, "unexpected {world:?}");
        assert!((world[1] + 4.242_641).abs() < 1e-5, "unexpected {world:?}");
        let wrong = [
            dx * theta.cos() - dy * theta.sin(),
            dx * theta.sin() + dy * theta.cos(),
        ];
        assert!(
            distance(world, [9.899_495, -4.242_641]) < distance(wrong, [9.899_495, -4.242_641]),
            "oracle must prefer R(-theta)"
        );
    }
}
