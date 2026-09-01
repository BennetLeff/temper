//! Fail-closed authority for immutable regional PCB topology declarations.
//!
//! The production board remains the source of object identity. This module
//! validates declarations against board bytes and predecessor evidence; it
//! never edits or materializes a board.

#[cfg(feature = "python")]
use pyo3::types::PyModuleMethods;
use serde::Serialize;
use serde_json::{Value, json};
use std::collections::{BTreeMap, BTreeSet};

pub const DECLARATION_SCHEMA: &str = "temper-regional-topology-declaration/v2";
pub const BASIS_SCHEMA: &str = "temper-regional-topology-design-basis/v1";
pub const RECEIPT_SCHEMA: &str = "temper-regional-topology-validation/v1";

pub fn candidate_digest<T: Serialize>(identity: &T) -> Result<String, String> {
    let canonical = serde_json::to_value(identity)
        .map_err(|error| format!("failed to canonicalize topology identity: {error}"))?;
    let bytes = serde_json::to_vec(&canonical)
        .map_err(|error| format!("failed to serialize topology identity: {error}"))?;
    Ok(crate::sha256(&bytes))
}

#[derive(Debug, Serialize)]
struct BoardTopologySnapshot {
    net41_segment_count: usize,
    net41_via_count: usize,
    net41_zone_count: usize,
    net41_pad_ids: BTreeSet<String>,
    net41_component_count: usize,
    net41_isolated_pad_ids: BTreeSet<String>,
    net41_pad_positions: BTreeMap<String, [f64; 2]>,
    selv_object_counts: BTreeMap<&'static str, usize>,
    selv_identity_digest: String,
}

fn point_key(point: [f64; 2]) -> String {
    format!("{:.6},{:.6}", point[0], point[1])
}

fn footprint_reference(footprint: &crate::parse_engine::RawFootprint) -> Option<&str> {
    footprint
        .properties
        .iter()
        .find(|(key, _)| key == "Reference")
        .map(|(_, value)| value.as_str())
}

fn pad_world_position(
    footprint: &crate::parse_engine::RawFootprint,
    pad: &crate::parse_engine::RawPad,
) -> [f64; 2] {
    let theta = footprint
        .position
        .angle
        .unwrap_or(crate::parse_engine::Num::I(0));
    let radians = theta.as_f64().to_radians();
    let (cosine, sine) = (radians.cos(), radians.sin());
    let (x, y) = (pad.position.x.as_f64(), pad.position.y.as_f64());
    [
        footprint.position.x.as_f64() + x * cosine + y * sine,
        footprint.position.y.as_f64() - x * sine + y * cosine,
    ]
}

fn board_topology_snapshot(
    board_text: &str,
    domain_manifest_text: &str,
) -> Result<BoardTopologySnapshot, String> {
    use crate::parse_engine::RawTraceItem;

    let board = crate::parse_engine::parse_kicad_document(board_text)?;
    let manifest: Value = serde_yaml::from_str(domain_manifest_text)
        .map_err(|error| format!("invalid domain manifest YAML: {error}"))?;
    let selv_nets: BTreeSet<_> = array(&manifest, "/domains/SELV/nets")?
        .iter()
        .map(|value| {
            value
                .as_str()
                .ok_or_else(|| "SELV net names must be strings".to_string())
        })
        .collect::<Result<_, _>>()?;
    if selv_nets.is_empty() {
        return Err("domain manifest declares zero SELV nets".into());
    }
    let net_names: BTreeMap<_, _> = board
        .nets
        .iter()
        .map(|net| (net.number.as_f64() as i64, net.name.as_str()))
        .collect();

    let mut net41_segment_count = 0;
    let mut net41_via_count = 0;
    let mut adjacency: BTreeMap<String, BTreeSet<String>> = BTreeMap::new();
    let mut selv_tracks = BTreeSet::new();
    let mut selv_vias = BTreeSet::new();
    for trace in &board.trace_items {
        match trace {
            RawTraceItem::Segment {
                start,
                end,
                width,
                layer,
                net,
            } => {
                let net_number = net.as_f64() as i64;
                let start_point = [start.x.as_f64(), start.y.as_f64()];
                let end_point = [end.x.as_f64(), end.y.as_f64()];
                if net_number == 41 {
                    net41_segment_count += 1;
                    if layer != "In3.Cu" || width.as_f64().to_bits() != 0.5f64.to_bits() {
                        return Err("net-41 segment changed layer or width".into());
                    }
                    let start_key = point_key(start_point);
                    let end_key = point_key(end_point);
                    adjacency
                        .entry(start_key.clone())
                        .or_default()
                        .insert(end_key.clone());
                    adjacency.entry(end_key).or_default().insert(start_key);
                }
                if net_names
                    .get(&net_number)
                    .is_some_and(|name| selv_nets.contains(name))
                {
                    selv_tracks.insert(format!(
                        "segment:{net_number}:{layer}:{:.6}:{:.6}:{:.6}:{:.6}:{:.6}",
                        start_point[0],
                        start_point[1],
                        end_point[0],
                        end_point[1],
                        width.as_f64()
                    ));
                }
            }
            RawTraceItem::Via {
                position,
                size,
                drill,
                layers,
                net,
            } => {
                let net_number = net.as_f64() as i64;
                let point = [position.x.as_f64(), position.y.as_f64()];
                if net_number == 41 {
                    net41_via_count += 1;
                    if size.as_f64().to_bits() != 0.9f64.to_bits()
                        || drill.as_f64().to_bits() != 0.3f64.to_bits()
                        || layers != &["In3.Cu".to_string(), "F.Cu".to_string()]
                    {
                        return Err("net-41 via changed size, drill, or span".into());
                    }
                    adjacency.entry(point_key(point)).or_default();
                }
                if net_names
                    .get(&net_number)
                    .is_some_and(|name| selv_nets.contains(name))
                {
                    selv_vias.insert(format!(
                        "via:{net_number}:{}:{:.6}:{:.6}:{:.6}:{:.6}",
                        layers.join("/"),
                        point[0],
                        point[1],
                        size.as_f64(),
                        drill.as_f64()
                    ));
                }
            }
            RawTraceItem::Arc { net, .. } | RawTraceItem::Target { net, .. } => {
                let net_number = net.as_f64() as i64;
                if net_number == 41
                    || net_names
                        .get(&net_number)
                        .is_some_and(|name| selv_nets.contains(name))
                {
                    return Err(
                        "regional authority does not support net-41 or SELV arc/target copper"
                            .into(),
                    );
                }
            }
        }
    }

    let mut net41_pad_ids = BTreeSet::new();
    let mut net41_pad_positions = BTreeMap::new();
    let mut selv_pads = BTreeSet::new();
    for footprint in &board.footprints {
        let reference = footprint_reference(footprint).unwrap_or("");
        for pad in &footprint.pads {
            let Some((net_number, net_name)) = &pad.net else {
                continue;
            };
            let point = pad_world_position(footprint, pad);
            let pad_id = format!("{reference}.{}", pad.number);
            if net_number.as_f64() as i64 == 41 {
                net41_pad_ids.insert(pad_id.clone());
                net41_pad_positions.insert(pad_id.clone(), point);
                adjacency.entry(point_key(point)).or_default();
            }
            if selv_nets.contains(net_name.as_str()) {
                selv_pads.insert(format!(
                    "pad:{pad_id}:{net_name}:{:.6}:{:.6}:{}",
                    point[0],
                    point[1],
                    pad.layers.join("/")
                ));
            }
        }
    }
    let mut selv_zones = BTreeSet::new();
    let mut net41_zone_count = 0;
    for zone in &board.zones {
        if zone.net_name.as_deref() == net_names.get(&41).copied() {
            net41_zone_count += 1;
        }
        if zone
            .net_name
            .as_deref()
            .is_some_and(|name| selv_nets.contains(name))
        {
            let polygon: Vec<_> = zone
                .polygons
                .iter()
                .flat_map(|points| points.iter())
                .map(|point| [point.x.as_f64(), point.y.as_f64()])
                .collect();
            selv_zones.insert(format!(
                "zone:{}:{}:{}",
                zone.net_name.as_deref().unwrap_or(""),
                zone.layers.join("/"),
                candidate_digest(&polygon)?
            ));
        }
    }

    let mut visited = BTreeSet::new();
    let mut component_count = 0;
    for start in adjacency.keys() {
        if visited.contains(start) {
            continue;
        }
        component_count += 1;
        let mut stack = vec![start.clone()];
        while let Some(node) = stack.pop() {
            if !visited.insert(node.clone()) {
                continue;
            }
            if let Some(neighbors) = adjacency.get(&node) {
                stack.extend(neighbors.iter().cloned());
            }
        }
    }
    let net41_isolated_pad_ids = net41_pad_positions
        .iter()
        .filter(|(_, point)| {
            adjacency
                .get(&point_key(**point))
                .is_some_and(BTreeSet::is_empty)
        })
        .map(|(pad_id, _)| pad_id.clone())
        .collect();
    let mut all_selv_identities = Vec::new();
    all_selv_identities.extend(selv_pads.iter().cloned());
    all_selv_identities.extend(selv_tracks.iter().cloned());
    all_selv_identities.extend(selv_vias.iter().cloned());
    all_selv_identities.extend(selv_zones.iter().cloned());
    if all_selv_identities.is_empty() {
        return Err("production board contains zero SELV copper objects".into());
    }
    let selv_object_counts = BTreeMap::from([
        ("pads", selv_pads.len()),
        ("tracks", selv_tracks.len()),
        ("vias", selv_vias.len()),
        ("zones", selv_zones.len()),
    ]);
    Ok(BoardTopologySnapshot {
        net41_segment_count,
        net41_via_count,
        net41_zone_count,
        net41_pad_ids,
        net41_component_count: component_count,
        net41_isolated_pad_ids,
        net41_pad_positions,
        selv_object_counts,
        selv_identity_digest: candidate_digest(&all_selv_identities)?,
    })
}

fn string<'a>(value: &'a Value, pointer: &str) -> Result<&'a str, String> {
    value
        .pointer(pointer)
        .and_then(Value::as_str)
        .ok_or_else(|| format!("missing string {pointer}"))
}

fn usize_at(value: &Value, pointer: &str) -> Result<usize, String> {
    value
        .pointer(pointer)
        .and_then(Value::as_u64)
        .and_then(|number| usize::try_from(number).ok())
        .ok_or_else(|| format!("missing integer {pointer}"))
}

fn array<'a>(value: &'a Value, pointer: &str) -> Result<&'a Vec<Value>, String> {
    value
        .pointer(pointer)
        .and_then(Value::as_array)
        .ok_or_else(|| format!("missing array {pointer}"))
}

fn exact_unique_strings(value: &Value, pointer: &str, expected: &[&str]) -> Result<(), String> {
    let rows = array(value, pointer)?;
    let actual: BTreeSet<_> = rows.iter().filter_map(Value::as_str).collect();
    let expected: BTreeSet<_> = expected.iter().copied().collect();
    if actual.len() != rows.len() || actual != expected {
        return Err(format!(
            "{pointer} is incomplete, duplicated, or unsupported"
        ));
    }
    Ok(())
}

fn validate_basis_authorization(basis: &Value) -> Result<(), String> {
    if string(basis, "/authorization/scope")? != "bounded-scratch-screening-and-routing-only"
        || basis
            .pointer("/authorization/fabrication_release")
            .and_then(Value::as_bool)
            != Some(false)
        || basis
            .pointer("/authorization/qualified_safety_approval")
            .and_then(Value::as_bool)
            != Some(false)
        || basis
            .pointer("/authorization/production_promotion")
            .and_then(Value::as_bool)
            != Some(false)
    {
        return Err("design basis overclaims its authorization".into());
    }
    Ok(())
}

pub fn authority_digest_without_receipts(declaration: &Value) -> Result<String, String> {
    let mut core = declaration.clone();
    let object = core
        .as_object_mut()
        .ok_or_else(|| "declaration must be an object".to_string())?;
    object.remove("declaration_authority_digest");
    object.remove("candidate_set_digest");
    candidate_digest(&core)
}

pub fn validate_declaration(
    declaration_json: &str,
    basis_json: &str,
    board_text: &str,
    predecessor_receipt_json: &str,
    predecessor_manifest_json: &str,
    domain_manifest_text: &str,
    netlist_text: &str,
    kicad_dru_text: &str,
    candidate_set_json: &str,
) -> Result<Value, String> {
    let declaration: Value = serde_json::from_str(declaration_json)
        .map_err(|error| format!("invalid declaration JSON: {error}"))?;
    let basis: Value = serde_json::from_str(basis_json)
        .map_err(|error| format!("invalid design-basis JSON: {error}"))?;
    let predecessor_receipt: Value = serde_json::from_str(predecessor_receipt_json)
        .map_err(|error| format!("invalid predecessor receipt JSON: {error}"))?;
    let predecessor_manifest: Value = serde_json::from_str(predecessor_manifest_json)
        .map_err(|error| format!("invalid predecessor manifest JSON: {error}"))?;
    let candidate_set: Value = serde_json::from_str(candidate_set_json)
        .map_err(|error| format!("invalid candidate-set JSON: {error}"))?;

    if string(&declaration, "/schema_version")? != DECLARATION_SCHEMA
        || string(&declaration, "/status")? != "declared"
        || string(&basis, "/schema_version")? != BASIS_SCHEMA
    {
        return Err("unsupported declaration, lifecycle status, or design-basis schema".into());
    }
    if string(&predecessor_receipt, "/status")? != "stopped-indeterminate"
        || string(&declaration, "/predecessor/relation")? != "new-design-hypothesis"
        || string(&declaration, "/predecessor/accepted_status")? != "stopped-indeterminate"
    {
        return Err("predecessor does not authorize this non-exhaustive successor family".into());
    }

    let board_sha256 = crate::sha256(board_text.as_bytes());
    let basis_sha256 = crate::sha256(basis_json.as_bytes());
    let receipt_sha256 = crate::sha256(predecessor_receipt_json.as_bytes());
    let manifest_sha256 = crate::sha256(predecessor_manifest_json.as_bytes());
    let domain_sha256 = crate::sha256(domain_manifest_text.as_bytes());
    let netlist_sha256 = crate::sha256(netlist_text.as_bytes());
    let kicad_dru_sha256 = crate::sha256(kicad_dru_text.as_bytes());
    for (pointer, actual) in [
        ("/production_board_sha256", board_sha256.as_str()),
        ("/design_basis_sha256", basis_sha256.as_str()),
        ("/predecessor/receipt_sha256", receipt_sha256.as_str()),
        ("/predecessor/manifest_sha256", manifest_sha256.as_str()),
        (
            "/selv_denominator/domain_manifest_sha256",
            domain_sha256.as_str(),
        ),
        (
            "/generated_inputs/domain_manifest_sha256",
            domain_sha256.as_str(),
        ),
        ("/generated_inputs/netlist_sha256", netlist_sha256.as_str()),
        (
            "/generated_inputs/kicad_dru_sha256",
            kicad_dru_sha256.as_str(),
        ),
    ] {
        if string(&declaration, pointer)? != actual {
            return Err(format!("stale authority binding at {pointer}"));
        }
    }
    if string(&basis, "/production_board_sha256")? != board_sha256
        || string(&basis, "/topology_authority_digest")?
            != string(&declaration, "/topology_authority_digest")?
    {
        return Err("design basis is stale or overclaims its authorization".into());
    }
    validate_basis_authorization(&basis)?;
    let live_authority = crate::isolation_authority::authority_contract()?;
    if string(&declaration, "/topology_authority_digest")?
        != live_authority.topology_authority_digest
    {
        return Err("declaration uses a stale topology authority digest".into());
    }
    for (basis_pointer, declaration_pointer) in [
        ("/geometry/endpoint_x_mm", "/family/endpoint_x_mm"),
        ("/geometry/endpoint_y_mm", "/family/endpoint_y_mm"),
        ("/geometry/corridor_x_mm", "/family/corridor_x_mm"),
        ("/geometry/entry_y_mm", "/family/entry_y_mm"),
        ("/geometry/fixed_start", "/family/fixed_start"),
        ("/geometry/knee_y_mm", "/family/knee_y_mm"),
        ("/geometry/layer", "/family/layer"),
        ("/geometry/route_width_mm", "/family/route_width_mm"),
        ("/geometry/via/diameter_mm", "/family/via_diameter_mm"),
        ("/geometry/via/drill_mm", "/family/via_drill_mm"),
        ("/geometry/via/span", "/family/via_span"),
    ] {
        if basis.pointer(basis_pointer) != declaration.pointer(declaration_pointer) {
            return Err(format!(
                "design-basis geometry {basis_pointer} disagrees with {declaration_pointer}"
            ));
        }
    }
    let topology = board_topology_snapshot(board_text, domain_manifest_text)?;
    if topology.net41_segment_count != 15
        || topology.net41_via_count != 1
        || topology.net41_zone_count != 0
        || topology.net41_pad_ids != BTreeSet::from(["C7.1".to_string(), "R14.2".to_string()])
        || topology.net41_component_count != 2
        || topology.net41_isolated_pad_ids != BTreeSet::from(["C7.1".to_string()])
        || string(&declaration, "/route/predecessor_connectivity_status")? != "disconnected-at-C7.1"
    {
        return Err(
            "production net-41 graph no longer matches the declared disconnected predecessor"
                .into(),
        );
    }
    let c7_position = topology
        .net41_pad_positions
        .get("C7.1")
        .ok_or_else(|| "production net 41 lost C7.1".to_string())?;
    let r14_position = topology
        .net41_pad_positions
        .get("R14.2")
        .ok_or_else(|| "production net 41 lost R14.2".to_string())?;
    if declaration.pointer("/family/fixed_start") != Some(&json!(c7_position))
        || declaration.pointer("/family/endpoint_y_mm") != Some(&json!(r14_position[1]))
        || array(&declaration, "/family/endpoint_x_mm")?.first()
            != Some(&json!(r14_position[0] + 4.0))
    {
        return Err("candidate family is not anchored to the exact net-41 endpoint pads".into());
    }
    let declared_selv_counts = declaration
        .pointer("/selv_denominator/object_counts")
        .ok_or_else(|| "declaration omitted SELV object counts".to_string())?;
    if declared_selv_counts
        != &serde_json::to_value(&topology.selv_object_counts)
            .map_err(|error| format!("failed to serialize SELV counts: {error}"))?
        || string(&declaration, "/selv_denominator/identity_digest")?
            != topology.selv_identity_digest
    {
        return Err("complete SELV copper denominator changed".into());
    }

    exact_unique_strings(
        &declaration,
        "/selv_denominator/object_categories",
        &["pads", "tracks", "vias", "zones"],
    )?;
    exact_unique_strings(
        &declaration,
        "/allowed_mutations",
        &[
            "J1",
            "R45",
            "R58",
            "R66",
            "SW1",
            "U22",
            "R14",
            "net41_declared_route",
        ],
    )?;
    exact_unique_strings(
        &declaration,
        "/prohibited_mutations",
        &[
            "K1",
            "U8",
            "board_outline",
            "mounting_features",
            "connector_access",
            "unrelated_copper",
            "new_via_span",
            "manufacturing_slot",
        ],
    )?;

    let segment_ids = array(&declaration, "/route/existing_segment_tstamps")?;
    if segment_ids.len() != 15 {
        return Err("net-41 declaration must name exactly 15 existing segments".into());
    }
    let mut observed = BTreeSet::new();
    let via_id = string(&declaration, "/route/existing_via/tstamp")?;
    let tracked_ids: BTreeSet<_> = segment_ids
        .iter()
        .filter_map(Value::as_str)
        .chain(std::iter::once(via_id))
        .collect();
    let mut occurrence_counts: BTreeMap<&str, usize> =
        tracked_ids.iter().map(|id| (*id, 0)).collect();
    let mut object_lines = BTreeMap::new();
    let mut segment_count = 0;
    let mut zone_count = 0;
    for line in board_text.lines() {
        if line.contains("(segment") && line.contains("(net 41)") {
            segment_count += 1;
        }
        if line.contains("(zone") && line.contains("(net 41)") {
            zone_count += 1;
        }
        for id in &tracked_ids {
            if line.contains(id) {
                *occurrence_counts.entry(id).or_default() += 1;
                object_lines.entry(*id).or_insert(line);
            }
        }
    }
    for id in segment_ids {
        let id = id
            .as_str()
            .ok_or_else(|| "segment tstamp must be a string".to_string())?;
        if !observed.insert(id) || occurrence_counts.get(id) != Some(&1) {
            return Err(format!("segment identity {id} is missing or duplicated"));
        }
        let line = object_lines
            .get(id)
            .ok_or_else(|| format!("segment {id} disappeared"))?;
        if !line.contains("(segment")
            || !line.contains("(net 41)")
            || !line.contains("(layer \"In3.Cu\")")
        {
            return Err(format!("segment {id} changed net, object type, or layer"));
        }
    }
    if segment_count != topology.net41_segment_count {
        return Err(format!(
            "production board contains {segment_count} net-41 segments, expected 15"
        ));
    }
    let via_line = object_lines
        .get(via_id)
        .ok_or_else(|| "declared net-41 via disappeared".to_string())?;
    if occurrence_counts.get(via_id) != Some(&1)
        || !via_line.contains("(via blind")
        || !via_line.contains("(net 41)")
        || !via_line.contains("(layers \"In3.Cu\" \"F.Cu\")")
    {
        return Err("net-41 via identity, net, type, or span changed".into());
    }
    if zone_count != topology.net41_zone_count {
        return Err("net-41 unexpectedly gained a zone".into());
    }

    let placements: BTreeSet<_> = predecessor_manifest
        .pointer("/results")
        .and_then(Value::as_array)
        .ok_or_else(|| "predecessor manifest has no results".to_string())?
        .iter()
        .filter(|row| row.pointer("/east_shift_mm").and_then(Value::as_f64) == Some(4.0))
        .filter_map(|row| {
            row.pointer("/predecessor_placement_id")
                .and_then(Value::as_str)
        })
        .collect();
    if placements.len() != 60
        || usize_at(&declaration, "/family/predecessor_placement_count")? != 60
    {
        return Err("predecessor placement set is not the exact 60-row family".into());
    }
    let axes = [
        usize_at(&declaration, "/family/predecessor_placement_count")?,
        array(&declaration, "/family/endpoint_x_mm")?.len(),
        array(&declaration, "/family/corridor_x_mm")?.len(),
        array(&declaration, "/family/entry_y_mm")?.len(),
    ];
    let cardinality = axes
        .into_iter()
        .try_fold(1usize, |total, count| total.checked_mul(count))
        .ok_or_else(|| "candidate cardinality overflow".to_string())?;
    if cardinality != 2880 || usize_at(&declaration, "/family/candidate_budget")? != cardinality {
        return Err(format!(
            "corridor Cartesian product is {cardinality}, expected 2880"
        ));
    }
    if string(&candidate_set, "/schema_version")? != "temper-regional-corridor-declaration/v2"
        || usize_at(&candidate_set, "/candidate_count")? != cardinality
        || string(&candidate_set, "/declaration_hash")?
            != string(&declaration, "/declaration_authority_digest")?
        || string(&candidate_set, "/board_hash")?
            != string(&declaration, "/production_board_sha256")?
        || string(&candidate_set, "/topology_authority/digest")?
            != string(&declaration, "/topology_authority_digest")?
    {
        return Err("candidate set is stale or bound to a different authority".into());
    }
    let generated_hashes: BTreeSet<_> = array(&candidate_set, "/generated_input_hashes")?
        .iter()
        .filter_map(Value::as_str)
        .collect();
    let expected_generated_hashes: BTreeSet<_> = [
        domain_sha256.as_str(),
        netlist_sha256.as_str(),
        kicad_dru_sha256.as_str(),
    ]
    .into_iter()
    .collect();
    if generated_hashes.len() != 3 || generated_hashes != expected_generated_hashes {
        return Err("candidate set has stale or duplicated generated-input identities".into());
    }
    let candidate_set_digest = candidate_digest(array(&candidate_set, "/candidates")?)?;
    if string(&candidate_set, "/candidate_set_digest")? != candidate_set_digest
        || string(&declaration, "/candidate_set_digest")? != candidate_set_digest
    {
        return Err("candidate-set digest is stale".into());
    }
    let expected_authority_digest = authority_digest_without_receipts(&declaration)?;
    if string(&declaration, "/declaration_authority_digest")? != expected_authority_digest {
        return Err("declaration authority digest is stale".into());
    }

    Ok(json!({
        "schema_version": RECEIPT_SCHEMA,
        "valid": true,
        "production_board_sha256": board_sha256,
        "declaration_authority_digest": expected_authority_digest,
        "candidate_set_digest": candidate_set_digest,
        "candidate_count": cardinality,
        "predecessor_placement_count": placements.len(),
        "net41": {"segments": 15, "vias": 1, "zones": 0},
        "net41_predecessor_connectivity": "disconnected-at-C7.1",
        "selv_object_counts": topology.selv_object_counts,
        "selv_identity_digest": topology.selv_identity_digest,
        "topology_authority_digest": string(&declaration, "/topology_authority_digest")?,
    }))
}

#[cfg(feature = "python")]
#[pyo3::pyfunction]
fn regional_topology_snapshot_json_py(
    board_bytes: &[u8],
    domain_manifest_bytes: &[u8],
) -> pyo3::PyResult<String> {
    let board_text = std::str::from_utf8(board_bytes)
        .map_err(|error| pyo3::exceptions::PyValueError::new_err(error.to_string()))?;
    let domain_manifest_text = std::str::from_utf8(domain_manifest_bytes)
        .map_err(|error| pyo3::exceptions::PyValueError::new_err(error.to_string()))?;
    board_topology_snapshot(board_text, domain_manifest_text)
        .and_then(|value| serde_json::to_string(&value).map_err(|error| error.to_string()))
        .map_err(pyo3::exceptions::PyValueError::new_err)
}

#[cfg(feature = "python")]
#[pyo3::pyfunction]
fn validate_regional_topology_declaration_json_py(
    declaration_bytes: &[u8],
    basis_bytes: &[u8],
    board_bytes: &[u8],
    predecessor_receipt_bytes: &[u8],
    predecessor_manifest_bytes: &[u8],
    domain_manifest_bytes: &[u8],
    netlist_bytes: &[u8],
    kicad_dru_bytes: &[u8],
    candidate_set_bytes: &[u8],
) -> pyo3::PyResult<String> {
    fn decode(bytes: &[u8]) -> pyo3::PyResult<&str> {
        std::str::from_utf8(bytes)
            .map_err(|error| pyo3::exceptions::PyValueError::new_err(error.to_string()))
    }
    validate_declaration(
        decode(declaration_bytes)?,
        decode(basis_bytes)?,
        decode(board_bytes)?,
        decode(predecessor_receipt_bytes)?,
        decode(predecessor_manifest_bytes)?,
        decode(domain_manifest_bytes)?,
        decode(netlist_bytes)?,
        decode(kicad_dru_bytes)?,
        decode(candidate_set_bytes)?,
    )
    .and_then(|value| serde_json::to_string(&value).map_err(|error| error.to_string()))
    .map_err(pyo3::exceptions::PyValueError::new_err)
}

#[cfg(feature = "python")]
pub(crate) fn register(module: &pyo3::Bound<'_, pyo3::types::PyModule>) -> pyo3::PyResult<()> {
    module.add_function(pyo3::wrap_pyfunction!(
        regional_topology_snapshot_json_py,
        module
    )?)?;
    module.add_function(pyo3::wrap_pyfunction!(
        validate_regional_topology_declaration_json_py,
        module
    )?)
}

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

    #[cfg_attr(test, test)]
    fn candidate_digest_is_content_sensitive() {
        assert_ne!(
            candidate_digest(&("a", 1)).unwrap(),
            candidate_digest(&("a", 2)).unwrap()
        );
    }

    #[cfg_attr(test, test)]
    fn production_authorization_is_always_denied() {
        let baseline = json!({
            "authorization": {
                "scope": "bounded-scratch-screening-and-routing-only",
                "fabrication_release": false,
                "qualified_safety_approval": false,
                "production_promotion": false,
            }
        });
        assert!(validate_basis_authorization(&baseline).is_ok());
        for key in [
            "fabrication_release",
            "qualified_safety_approval",
            "production_promotion",
        ] {
            let mut changed = baseline.clone();
            changed["authorization"][key] = Value::Bool(true);
            assert!(validate_basis_authorization(&changed).is_err());
        }
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("regional_topology::tests::candidate_digest_is_content_sensitive", candidate_digest_is_content_sensitive),
        ("regional_topology::tests::production_authorization_is_always_denied", production_authorization_is_always_denied),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}
