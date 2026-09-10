//! MCU development-profile acceptance policy (P1 U3).
//!
//! Thin profile adapter over the shared runner/workspace/dispatch path. The
//! fixed buck assumptions that do NOT transfer are extracted into the task
//! contract supplied by `run_block.py` (movable refs, admitted nets,
//! obligations, keepouts, protected ports); Rust owns only shapes, numeric
//! limits, and evaluation semantics.
//!
//! Differences from `buck.rs` / `buck_operations.rs` (deliberate):
//! - Six-layer target context: tracks may sit on any contract-supported
//!   layer within the P3 physical copper order; through-vias still span
//!   exactly `F.Cu-B.Cu` with frozen 0.8/0.4 mm dimensions.
//! - Zone connectivity is measured: an obligation is satisfied only by native
//!   `CONNECTIVITY_DATA` clusters (zone UUIDs included), never by a
//!   straight-line pad-distance metric. `buck.rs` locality/separation metrics
//!   do not exist here.
//! - Missing/extra footprints are `fail` findings, not hard errors: a hidden
//!   part must read as a failed candidate, never as an indeterminate report.
//! - `protected_ports` and `keepouts` are contract data; the antenna keepout
//!   intrusion and moved-port scenarios fail through them.

use anyhow::{ensure, Context, Result};
use serde::Deserialize;
use serde_json::{json, Map, Value};
use std::collections::{BTreeMap, BTreeSet};

pub const MAX_ACTIONS: u64 = 200;
pub const MAX_SECONDS: f64 = 1200.0;
pub const MAX_OBJECTS: usize = 512;
// Native coordinate range. The MCU fixture is small, but the combined
// buck/MCU assembly occupies the real cooker board (164x234 mm, outline
// 8..172 x 20..254); a 200 mm cap clipped legitimate +3V3/gnd coordinates on
// that board. 400 mm covers the target with margin and does not change any
// admitted MCU/assembly geometry (every real coordinate is well inside it).
pub const MAX_COORD_MM: f64 = 400.0;
pub const MAX_EXECUTE_BYTES: usize = 65_536;

/// Reference P3 physical copper order (target-context.json). Operation policy
/// admits layers only within this order; the evaluation contract carries its
/// own order and Rust checks shape plus subset containment there.
const PHYSICAL_COPPER_ORDER: &[&str] = &["F.Cu", "In3.Cu", "In1.Cu", "In2.Cu", "In4.Cu", "B.Cu"];
const VIA_SPAN: &str = "F.Cu-B.Cu";
const VIA_DIAMETER_MM: f64 = 0.8;
const VIA_DRILL_MM: f64 = 0.4;

fn valid_copper_layer(name: &str) -> bool {
    if name == "F.Cu" || name == "B.Cu" {
        return true;
    }
    let inner = name.strip_suffix(".Cu").and_then(|s| s.strip_prefix("In"));
    inner.is_some_and(|n| !n.is_empty() && n.bytes().all(|c| c.is_ascii_digit()))
}

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
struct Track {
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
struct Cluster {
    pad: String,
    pads: Vec<String>,
    tracks: Vec<String>,
}

#[derive(Deserialize)]
struct BlockMeasurement {
    tracks: Vec<Track>,
    connectivity: Vec<Cluster>,
}

#[derive(Deserialize)]
struct Measurement {
    kicad_version: String,
    board_sha256: String,
    protected_sha256: String,
    footprints: Vec<Footprint>,
    block: BlockMeasurement,
}

#[derive(Deserialize)]
struct Port {
    position_mm: [f64; 2],
    net: String,
}

#[derive(Deserialize)]
struct Keepout {
    id: String,
    x1: f64,
    y1: f64,
    x2: f64,
    y2: f64,
}

#[derive(Deserialize)]
struct Contract {
    profile: String,
    kicad_version: String,
    protected_sha256: String,
    outline_mm: [f64; 4],
    physical_copper_order: Vec<String>,
    supported_layers: Vec<String>,
    allowed_copper_kinds: Vec<String>,
    min_power_width_mm: f64,
    min_signal_width_mm: f64,
    power_nets: Vec<String>,
    signal_nets: Vec<String>,
    movable_refs: Vec<String>,
    protected_ports: BTreeMap<String, Port>,
    pad_census: BTreeMap<String, usize>,
    net_mapping: BTreeMap<String, String>,
    obligations: BTreeMap<String, Vec<String>>,
    #[serde(default)]
    boundary: BTreeMap<String, Vec<String>>,
    #[serde(default)]
    keepouts: Vec<Keepout>,
    zone_nets: Vec<String>,
    via_diameter_mm: f64,
    via_drill_mm: f64,
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

fn distance(a: [f64; 2], b: [f64; 2]) -> f64 {
    (a[0] - b[0]).hypot(a[1] - b[1])
}

fn is_digest(value: &str) -> bool {
    value.len() == 64 && value.bytes().all(|c| c.is_ascii_hexdigit())
}

/// KiCad reports orientations clockwise; normalize any equivalent angle
/// (e.g. -90) into [0, 360) before comparison.
fn normalize_angle(angle_deg: f64) -> f64 {
    angle_deg.rem_euclid(360.0)
}

fn rects_intersect(a: [f64; 4], b: [f64; 4]) -> bool {
    a[0] < b[2] && b[0] < a[2] && a[1] < b[3] && b[1] < a[3]
}

pub fn evaluate(input: Input) -> Result<Value> {
    let Input {
        measurement: m,
        contract: c,
        drc,
    } = input;
    ensure!(c.profile == "block", "wrong task profile");
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
        "invalid block outline"
    );
    // The exact physical sequence is task-context data owned by the P1
    // host/P3 (pinned where the candidate is built); Rust checks shape and
    // containment so any well-formed stackup evaluates by the same rules.
    ensure!(
        !c.physical_copper_order.is_empty()
            && c.physical_copper_order
                .iter()
                .all(|l| valid_copper_layer(l.as_str()))
            && c.physical_copper_order
                .iter()
                .collect::<BTreeSet<_>>()
                .len()
                == c.physical_copper_order.len(),
        "physical copper order must list distinct copper layers"
    );
    ensure!(
        !c.supported_layers.is_empty()
            && c.supported_layers
                .iter()
                .all(|l| c.physical_copper_order.contains(l)),
        "supported layers must be a non-empty subset of the physical order"
    );
    for value in [
        c.min_power_width_mm,
        c.min_signal_width_mm,
        c.via_diameter_mm,
        c.via_drill_mm,
    ] {
        ensure!(value.is_finite() && value > 0.0, "invalid block rule");
    }
    ensure!(
        (c.via_diameter_mm - VIA_DIAMETER_MM).abs() < 1e-9
            && (c.via_drill_mm - VIA_DRILL_MM).abs() < 1e-9,
        "through-via dimensions are frozen at 0.8/0.4 mm"
    );
    ensure!(!c.movable_refs.is_empty(), "empty movable census");
    ensure!(
        c.movable_refs.len() == c.movable_refs.iter().collect::<BTreeSet<_>>().len(),
        "duplicate movable reference"
    );
    for r in &c.movable_refs {
        ensure!(
            !r.is_empty() && c.pad_census.contains_key(r),
            "movable reference without pad census: {r}"
        );
        ensure!(
            !c.protected_ports.contains_key(r),
            "reference cannot be both movable and protected: {r}"
        );
    }
    let expected_pads: BTreeSet<&str> = c.net_mapping.keys().map(String::as_str).collect();
    ensure!(!expected_pads.is_empty(), "empty block pad census");
    let mut census: BTreeMap<&str, usize> = BTreeMap::new();
    for pad in expected_pads.iter() {
        let reference = pad.split_once('.').context("invalid pad identity")?.0;
        *census.entry(reference).or_insert(0) += 1;
    }
    let mut expected_refs: BTreeSet<&str> = c.movable_refs.iter().map(String::as_str).collect();
    expected_refs.extend(c.protected_ports.keys().map(String::as_str));
    ensure!(
        census.keys().copied().collect::<BTreeSet<_>>() == expected_refs,
        "pad census must cover exactly the movable and protected references"
    );
    for (reference, count) in &c.pad_census {
        ensure!(
            census.get(reference.as_str()) == Some(count),
            "unexpected pad census for {reference}"
        );
    }
    ensure!(
        !c.zone_nets.is_empty()
            && c.zone_nets
                .iter()
                .all(|n| c.power_nets.contains(n) || c.signal_nets.contains(n)),
        "zone nets must be admitted nets"
    );

    let mut findings = Vec::new();

    // Census mismatch is a failed candidate (hidden part), never a missing
    // report: it must read as `fail`, not `indeterminate`.
    let seen: BTreeSet<&str> = m.footprints.iter().map(|f| f.reference.as_str()).collect();
    if seen.len() != m.footprints.len() {
        findings.push(json!({"id": "duplicate_footprint"}));
    }
    for r in expected_refs.iter() {
        if !seen.contains(r) {
            findings.push(json!({"id": format!("missing_footprint:{r}")}));
        }
    }
    for r in seen.iter() {
        if !expected_refs.contains(r) {
            findings.push(json!({"id": format!("extra_footprint:{r}")}));
        }
    }

    for fp in &m.footprints {
        if !expected_refs.contains(fp.reference.as_str()) {
            continue;
        }
        if !fp
            .position_mm
            .iter()
            .chain(fp.bounds_mm.iter())
            .chain([&fp.angle_deg])
            .all(|v| v.is_finite())
            || fp.bounds_mm[0] >= fp.bounds_mm[2]
            || fp.bounds_mm[1] >= fp.bounds_mm[3]
        {
            findings.push(json!({"id": format!("invalid_geometry:{}", fp.reference)}));
            continue;
        }
        let expected_count = c.pad_census.get(&fp.reference);
        if Some(&fp.pads.len()) != expected_count {
            findings.push(json!({"id": format!("unexpected_pad_census:{}", fp.reference)}));
            continue;
        }
        for p in &fp.pads {
            if !p.position_mm.iter().all(|v| v.is_finite()) {
                findings.push(json!({"id": format!("invalid_geometry:{}", fp.reference)}));
                continue;
            }
            let identity = format!("{}.{}", fp.reference, p.number);
            if c.net_mapping.get(&identity) != Some(&p.net) {
                findings.push(json!({"id": format!("net_mismatch:{identity}")}));
            }
        }
        let [x0, y0, x1, y1] = c.outline_mm;
        let [left, top, right, bottom] = fp.bounds_mm;
        if left < x0 || top < y0 || right > x1 || bottom > y1 {
            findings.push(json!({"id": format!("outside_outline:{}", fp.reference)}));
        }
        // Native KiCad may report an admitted pose as a negative
        // equivalent (-90 for 270); only orthogonal poses are admitted.
        let angle = normalize_angle(fp.angle_deg);
        if ![0.0, 90.0, 180.0, 270.0]
            .iter()
            .any(|a| (angle - a).abs() < 1e-6)
        {
            findings.push(json!({"id": format!("unsupported_orientation:{}", fp.reference)}));
        }
        for k in &c.keepouts {
            ensure!(
                k.x1.is_finite()
                    && k.y1.is_finite()
                    && k.x2.is_finite()
                    && k.y2.is_finite()
                    && k.x1 < k.x2
                    && k.y1 < k.y2
                    && !k.id.is_empty(),
                "invalid keepout contract"
            );
            if rects_intersect(fp.bounds_mm, [k.x1, k.y1, k.x2, k.y2]) {
                findings
                    .push(json!({"id": format!("keepout_intrusion:{}:{}", k.id, fp.reference)}));
            }
        }
    }

    if m.protected_sha256 != c.protected_sha256 {
        findings.push(json!({"id": "protected_state_changed"}));
    }
    for (reference, port) in &c.protected_ports {
        if let Ok(fp) = footprint(&m, reference) {
            ensure!(
                port.position_mm.iter().all(|v| v.is_finite()),
                "nonfinite protected port pose"
            );
            if distance(fp.position_mm, port.position_mm) > 1e-6 {
                findings.push(json!({"id": format!("protected_port_moved:{reference}")}));
            }
            for p in &fp.pads {
                if p.net != port.net {
                    findings.push(json!({"id": format!("net_mismatch:{reference}.{}", p.number)}));
                }
            }
        }
    }

    let clusters: BTreeMap<&str, &Cluster> = m
        .block
        .connectivity
        .iter()
        .map(|c| (c.pad.as_str(), c))
        .collect();
    if clusters.len() != m.block.connectivity.len()
        || clusters.keys().copied().collect::<BTreeSet<_>>() != expected_pads
    {
        findings.push(json!({"id": "incomplete_connectivity_census"}));
    }
    let tracks: BTreeMap<&str, &Track> = m
        .block
        .tracks
        .iter()
        .map(|t| (t.uuid.as_str(), t))
        .collect();
    if tracks.len() != m.block.tracks.len() || tracks.contains_key("") {
        findings.push(json!({"id": "invalid_track_identities"}));
    }
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
        if pads.len() != cluster.pads.len()
            || !pads.contains(cluster.pad.as_str())
            || !pads.is_subset(&expected_pads)
            || ids.len() != cluster.tracks.len()
            || !ids.iter().all(|id| tracks.contains_key(id))
        {
            findings.push(json!({"id": format!("invalid_cluster:{}", cluster.pad)}));
            continue;
        }
        for pad in &pads {
            if let Some(other) = clusters.get(pad) {
                let same_pads = other
                    .pads
                    .iter()
                    .map(String::as_str)
                    .collect::<BTreeSet<_>>()
                    == pads;
                let same_tracks = other
                    .tracks
                    .iter()
                    .map(String::as_str)
                    .collect::<BTreeSet<_>>()
                    == ids;
                if !same_pads || !same_tracks {
                    findings.push(json!({"id": format!("inconsistent_cluster:{}", cluster.pad)}));
                    break;
                }
            }
        }
        let nets: BTreeSet<&str> = pads
            .iter()
            .filter_map(|pad| c.net_mapping.get(*pad).map(String::as_str))
            .collect();
        if nets.len() != 1 {
            findings.push(json!({"id": format!("shorted_cluster:{}", cluster.pad)}));
            continue;
        }
        cluster_net.insert(cluster.pad.as_str(), *nets.iter().next().unwrap());
    }

    // Obligations (and boundary interfaces) are satisfied only by measured
    // native clusters. A zone pour counts through its UUID membership in the
    // native cluster, never through outline geometry.
    let check_obligations =
        |scope: &str, obligations: &BTreeMap<String, Vec<String>>, findings: &mut Vec<Value>| {
            for (net, pads) in obligations {
                if !admitted.contains(net.as_str()) {
                    findings.push(json!({"id": format!("{scope}_unadmitted_net:{net}")}));
                    continue;
                }
                if pads.is_empty() {
                    findings.push(json!({"id": format!("{scope}_empty_obligation:{net}")}));
                    continue;
                }
                let Some(first) = pads.first() else {
                    continue;
                };
                let Some(anchor) = clusters.get(first.as_str()) else {
                    findings.push(json!({"id": format!("{scope}_missing_cluster:{first}")}));
                    continue;
                };
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
        };
    check_obligations("internal", &c.obligations, &mut findings);
    check_obligations("boundary", &c.boundary, &mut findings);

    for track in tracks.values() {
        if !track
            .start_mm
            .iter()
            .chain(track.end_mm.iter())
            .chain(track.bounds_mm.iter())
            .chain([&track.width_mm])
            .all(|v| v.is_finite())
            || track.width_mm <= 0.0
            || track.bounds_mm[0] > track.bounds_mm[2]
            || track.bounds_mm[1] > track.bounds_mm[3]
        {
            findings.push(json!({"id": format!("invalid_track_geometry:{}", track.uuid)}));
            continue;
        }
        let layer_ok = c.supported_layers.contains(&track.layer)
            || (track.kind == "via" && track.layer == VIA_SPAN);
        if !c.allowed_copper_kinds.contains(&track.kind)
            || !layer_ok
            || !admitted.contains(track.net.as_str())
        {
            findings.push(json!({"id": format!("unsupported_track:{}", track.uuid)}));
            continue;
        }
        if track.kind == "via" && track.layer != VIA_SPAN {
            findings.push(json!({"id": format!("unsupported_track:{}", track.uuid)}));
            continue;
        }
        if track.kind == "zone" && !c.zone_nets.contains(&track.net) {
            findings.push(json!({"id": format!("unsupported_zone_net:{}", track.uuid)}));
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
        for k in &c.keepouts {
            if rects_intersect(track.bounds_mm, [k.x1, k.y1, k.x2, k.y2]) {
                findings.push(json!({"id": format!("keepout_intrusion:{}:{}", k.id, track.uuid)}));
            }
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
            .filter_map(|pad| c.net_mapping.get(pad.as_str()).map(String::as_str))
            .collect();
        if !member_nets.contains(track.net.as_str()) {
            findings.push(json!({"id": format!("wrong_net:{}", track.uuid)}));
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
        "scope": "mcu_block", "board_sha256": m.board_sha256,
        "findings": findings,
        "open_connection_evidence": drc.unconnected_items}),
    )
}

fn finite(v: &Value) -> bool {
    v.as_f64().is_some_and(f64::is_finite)
}

fn point(v: &Value, limit: f64) -> bool {
    v.as_array().is_some_and(|a| {
        a.len() == 2
            && a.iter()
                .all(|coordinate| finite(coordinate) && coordinate.as_f64().unwrap().abs() <= limit)
    })
}

fn exact_keys(object: &Map<String, Value>, keys: &[&str], message: &str) -> Result<()> {
    ensure!(
        object.len() == keys.len() && keys.iter().all(|key| object.contains_key(*key)),
        "{message}"
    );
    Ok(())
}

struct OperationContext<'a> {
    movable_refs: &'a Vec<Value>,
    admitted_nets: &'a Vec<Value>,
    supported_layers: &'a Vec<Value>,
    outline: [f64; 4],
}

fn operation_context(input: &Value) -> Result<OperationContext<'_>> {
    let context = input.get("context").context("missing operation context")?;
    let refs = context
        .get("movable_refs")
        .and_then(Value::as_array)
        .context("context needs movable_refs")?;
    ensure!(!refs.is_empty(), "empty movable census");
    let nets = context
        .get("admitted_nets")
        .and_then(Value::as_array)
        .context("context needs admitted_nets")?;
    ensure!(!nets.is_empty(), "empty admitted nets");
    let layers = context
        .get("supported_layers")
        .and_then(Value::as_array)
        .context("context needs supported_layers")?;
    ensure!(!layers.is_empty(), "empty supported layers");
    for layer in layers {
        let name = layer.as_str().context("layer must be a string")?;
        ensure!(
            PHYSICAL_COPPER_ORDER.contains(&name),
            "layer outside the physical copper order: {name}"
        );
    }
    let outline = context
        .get("outline_mm")
        .and_then(Value::as_array)
        .context("context needs outline_mm")?;
    ensure!(outline.len() == 4, "outline must have four coordinates");
    let mut corners = [0.0; 4];
    for (i, v) in outline.iter().enumerate() {
        corners[i] = v.as_f64().context("outline must be numeric")?;
        ensure!(corners[i].is_finite(), "outline must be finite");
    }
    ensure!(
        corners[0] < corners[2] && corners[1] < corners[3],
        "invalid outline context"
    );
    Ok(OperationContext {
        movable_refs: refs,
        admitted_nets: nets,
        supported_layers: layers,
        outline: corners,
    })
}

fn schema() -> Value {
    let coordinate = json!({"type":"number", "minimum":-MAX_COORD_MM, "maximum":MAX_COORD_MM});
    let width = json!({"type":"number", "minimum":0.2, "maximum":2.0});
    let point = json!({"type":"array", "minItems":2, "maxItems":2, "items":coordinate});
    json!({
        "max_actions": MAX_ACTIONS, "max_seconds": MAX_SECONDS,
        "max_objects": MAX_OBJECTS, "max_execute_bytes": MAX_EXECUTE_BYTES,
        "tools": [
            {"name":"inspect", "description":"Inspect the saved MCU block board.", "inputSchema":{"type":"object","properties":{},"additionalProperties":false}},
            {"name":"check", "description":"Reload and independently evaluate the board.", "inputSchema":{"type":"object","properties":{},"additionalProperties":false}},
            {"name":"place", "description":"Place one movable MCU footprint; copper remains stationary.", "inputSchema":{"type":"object","properties":{"reference":{"type":"string"},"x_mm":coordinate,"y_mm":coordinate,"angle_deg":{"type":"integer","enum":[0,90,180,270]}},"required":["reference","x_mm","y_mm","angle_deg"],"additionalProperties":false}},
            {"name":"replace_copper", "description":"Atomically replace all mutable copper for one admitted net.", "inputSchema":{"type":"object","properties":{"net":{"type":"string"},"segments":{"type":"array","maxItems":MAX_OBJECTS,"items":{"type":"object","properties":{"start_mm":point,"end_mm":point,"layer":{"type":"string"},"width_mm":width},"required":["start_mm","end_mm","layer","width_mm"],"additionalProperties":false}},"vias":{"type":"array","maxItems":MAX_OBJECTS,"items":{"type":"object","properties":{"position_mm":point,"diameter_mm":{"type":"number","const":0.8},"drill_mm":{"type":"number","const":0.4}},"required":["position_mm","diameter_mm","drill_mm"],"additionalProperties":false}},"zones":{"type":"array","maxItems":MAX_OBJECTS,"items":{"type":"object","properties":{"layer":{"type":"string"},"outline_mm":{"type":"array","minItems":3,"maxItems":64,"items":point}},"required":["layer","outline_mm"],"additionalProperties":false}}},"required":["net","segments","vias","zones"],"additionalProperties":false}},
            {"name":"execute", "description":"Reserved for the P2 persistent interpreter boundary.", "inputSchema":{"type":"object","properties":{"code":{"type":"string","maxLength":MAX_EXECUTE_BYTES}},"required":["code"],"additionalProperties":false}}
        ]
    })
}

/// Operation policy for profile `block-operation`. Movable refs, admitted
/// nets, and supported layers come from the host task contract (extracted
/// buck assumptions); shapes and numeric limits live here.
pub fn validate(input: Value) -> Result<Value> {
    let operation = input
        .get("operation")
        .and_then(Value::as_str)
        .ok_or_else(|| anyhow::anyhow!("missing operation"))?;
    let args = input
        .get("arguments")
        .and_then(Value::as_object)
        .ok_or_else(|| anyhow::anyhow!("arguments must be an object"))?;
    if operation == "schema" {
        ensure!(args.is_empty(), "schema takes no arguments");
        return Ok(schema());
    }
    match operation {
        "inspect" | "check" => ensure!(args.is_empty(), "{operation} takes no arguments"),
        "execute" => {
            exact_keys(args, &["code"], "execute requires exact keys")?;
            ensure!(
                args["code"]
                    .as_str()
                    .is_some_and(|code| code.len() <= MAX_EXECUTE_BYTES),
                "code must be a UTF-8 string of at most 65536 bytes"
            );
        }
        "place" => {
            exact_keys(
                args,
                &["reference", "x_mm", "y_mm", "angle_deg"],
                "place requires exact keys",
            )?;
            let ctx = operation_context(&input)?;
            let (refs, corners) = (ctx.movable_refs, ctx.outline);
            let reference = args["reference"]
                .as_str()
                .ok_or_else(|| anyhow::anyhow!("reference must be a string"))?;
            ensure!(
                refs.iter().any(|r| r.as_str() == Some(reference)),
                "reference is protected or unknown"
            );
            ensure!(
                finite(&args["x_mm"]) && finite(&args["y_mm"]),
                "coordinates must be finite"
            );
            let (x, y) = (
                args["x_mm"].as_f64().unwrap(),
                args["y_mm"].as_f64().unwrap(),
            );
            ensure!(
                x.abs() <= MAX_COORD_MM && y.abs() <= MAX_COORD_MM,
                "coordinates exceed native range"
            );
            let angle = args["angle_deg"]
                .as_i64()
                .ok_or_else(|| anyhow::anyhow!("angle must be an integer"))?;
            ensure!(
                [0, 90, 180, 270].contains(&angle),
                "angle must be 0, 90, 180, or 270"
            );
            let [x0, y0, x1, y1] = corners;
            ensure!(
                (x0..=x1).contains(&x) && (y0..=y1).contains(&y),
                "footprint origin must be inside the outline"
            );
        }
        "replace_copper" => {
            exact_keys(
                args,
                &["net", "segments", "vias", "zones"],
                "replace_copper requires exact keys",
            )?;
            let ctx = operation_context(&input)?;
            let (nets, layers) = (ctx.admitted_nets, ctx.supported_layers);
            let net = args["net"]
                .as_str()
                .ok_or_else(|| anyhow::anyhow!("net must be a string"))?;
            ensure!(nets.iter().any(|n| n.as_str() == Some(net)), "unknown net");
            let supported: Vec<&str> = layers.iter().filter_map(Value::as_str).collect();
            let zone_nets: Vec<&str> = input
                .get("context")
                .and_then(|c| c.get("zone_nets"))
                .and_then(Value::as_array)
                .context("context needs zone_nets")?
                .iter()
                .filter_map(Value::as_str)
                .collect();
            ensure!(!zone_nets.is_empty(), "empty zone nets");
            let segments = args["segments"]
                .as_array()
                .ok_or_else(|| anyhow::anyhow!("segments must be an array"))?;
            let vias = args["vias"]
                .as_array()
                .ok_or_else(|| anyhow::anyhow!("vias must be an array"))?;
            let zones = args["zones"]
                .as_array()
                .ok_or_else(|| anyhow::anyhow!("zones must be an array"))?;
            ensure!(
                segments.len() <= MAX_OBJECTS
                    && vias.len() <= MAX_OBJECTS
                    && zones.len() <= MAX_OBJECTS,
                "object limit exceeded"
            );
            for segment in segments {
                let object = segment
                    .as_object()
                    .ok_or_else(|| anyhow::anyhow!("segment must be an object"))?;
                exact_keys(
                    object,
                    &["start_mm", "end_mm", "layer", "width_mm"],
                    "invalid segment keys",
                )?;
                ensure!(
                    point(&object["start_mm"], MAX_COORD_MM)
                        && point(&object["end_mm"], MAX_COORD_MM),
                    "invalid segment points"
                );
                ensure!(
                    supported.contains(&object["layer"].as_str().unwrap_or("")),
                    "invalid segment layer"
                );
                ensure!(
                    finite(&object["width_mm"])
                        && (0.2..=2.0).contains(&object["width_mm"].as_f64().unwrap()),
                    "invalid segment width"
                );
            }
            for via in vias {
                let object = via
                    .as_object()
                    .ok_or_else(|| anyhow::anyhow!("via must be an object"))?;
                exact_keys(
                    object,
                    &["position_mm", "diameter_mm", "drill_mm"],
                    "invalid via keys",
                )?;
                ensure!(
                    point(&object["position_mm"], MAX_COORD_MM),
                    "invalid via position"
                );
                ensure!(
                    object["diameter_mm"].as_f64() == Some(VIA_DIAMETER_MM)
                        && object["drill_mm"].as_f64() == Some(VIA_DRILL_MM),
                    "vias must use frozen 0.8/0.4 mm dimensions"
                );
            }
            for zone in zones {
                let object = zone
                    .as_object()
                    .ok_or_else(|| anyhow::anyhow!("zone must be an object"))?;
                exact_keys(object, &["layer", "outline_mm"], "invalid zone keys")?;
                ensure!(
                    zone_nets.contains(&net)
                        && supported.contains(&object["layer"].as_str().unwrap_or("")),
                    "only admitted zone nets on supported layers are allowed"
                );
                let outline = object["outline_mm"]
                    .as_array()
                    .ok_or_else(|| anyhow::anyhow!("invalid zone outline"))?;
                ensure!(
                    (3..=64).contains(&outline.len())
                        && outline.iter().all(|p| point(p, MAX_COORD_MM)),
                    "invalid zone outline"
                );
            }
        }
        _ => ensure!(false, "unknown operation"),
    }
    Ok(
        json!({"status":"pass", "operation":operation, "max_actions":MAX_ACTIONS, "max_seconds":MAX_SECONDS, "max_objects":MAX_OBJECTS}),
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    fn context() -> Value {
        json!({
            "outline_mm": [8.0, 20.0, 172.0, 254.0],
            "movable_refs": ["U1", "C1"],
            "admitted_nets": ["vcc", "gnd"],
            "supported_layers": ["F.Cu", "B.Cu"],
            "zone_nets": ["gnd"],
        })
    }

    #[test]
    fn place_rejects_unlisted_reference() {
        assert!(validate(json!({"operation":"place",
            "arguments":{"reference":"J1","x_mm":30,"y_mm":40,"angle_deg":0},
            "context": context()}))
        .is_err());
    }

    #[test]
    fn place_accepts_listed_reference_inside_outline() {
        assert!(validate(json!({"operation":"place",
            "arguments":{"reference":"U1","x_mm":30,"y_mm":40,"angle_deg":90},
            "context": context()}))
        .is_ok());
    }

    #[test]
    fn place_rejects_inner_layer_zone_but_accepts_outer_track() {
        let ok = validate(json!({"operation":"replace_copper",
            "arguments":{"net":"gnd","segments":[
                {"start_mm":[30,40],"end_mm":[31,40],"layer":"In1.Cu","width_mm":0.5}],
                "vias":[],"zones":[]},
            "context": {
                "outline_mm": [8.0, 20.0, 172.0, 254.0],
                "movable_refs": ["U1"], "admitted_nets": ["vcc", "gnd"],
                "supported_layers": ["F.Cu", "In1.Cu", "B.Cu"],
                "zone_nets": ["gnd"]}}));
        assert!(ok.is_ok());
        let zoned = validate(json!({"operation":"replace_copper",
            "arguments":{"net":"vcc","segments":[],"vias":[],
                "zones":[{"layer":"F.Cu","outline_mm":[[30,40],[31,40],[30,41]]}]},
            "context": context()}))
        .is_err();
        assert!(zoned);
    }

    #[test]
    fn operation_without_task_context_is_invalid() {
        assert!(validate(json!({"operation":"place",
            "arguments":{"reference":"U1","x_mm":30,"y_mm":40,"angle_deg":0}}))
        .is_err());
    }

    #[test]
    fn schema_contains_nested_shapes() {
        let value = validate(json!({"operation":"schema","arguments":{}})).unwrap();
        assert_eq!(value["tools"].as_array().unwrap().len(), 5);
        assert!(value.to_string().contains("start_mm"));
    }

    #[test]
    fn asymmetric_oracle_probe_uses_kicad_clockwise_rotation() {
        // pcbnew ground truth: local offset (10, 4) at 45 deg lands at
        // (9.899495, -4.242641) under KiCad's clockwise R(-theta).
        // world = pos + R(-theta) . offset; R(+theta) is wrong here.
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

    #[test]
    fn negative_angles_normalize_to_positive_equivalents() {
        assert!((normalize_angle(-90.0) - 270.0).abs() < 1e-9);
        assert!((normalize_angle(450.0) - 90.0).abs() < 1e-9);
        assert!((normalize_angle(0.0) - 0.0).abs() < 1e-9);
    }
}
