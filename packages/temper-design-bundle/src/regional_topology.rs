//! Fail-closed authority for immutable regional PCB topology declarations.
//!
//! The production board remains the source of object identity. This module
//! validates declarations against board bytes and predecessor evidence; it
//! never edits or materializes a board.

#[cfg(feature = "python")]
use pyo3::types::PyModuleMethods;
use serde::Serialize;
use serde_json::{json, Value};
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

/// Hash an Atopile-generated netlist after removing checkout-root noise from
/// component sheet paths. Atopile writes the absolute build path into every
/// `(sheetpath (names "..."))` record, so hashing the raw file makes identical
/// electrical sources disagree between a developer worktree and CI.
pub fn netlist_identity_sha256(netlist_text: &str) -> Result<String, String> {
    const SHEETPATH_PREFIX: &str = "(sheetpath (names \"";
    const SOURCE_MARKER: &str = "/elec/src/";

    let normalized = netlist_text.replace("\r\n", "\n");
    let mut canonical = String::with_capacity(normalized.len());
    let mut cursor = 0;
    let mut sheetpath_count = 0;
    while let Some(relative_start) = normalized[cursor..].find(SHEETPATH_PREFIX) {
        let value_start = cursor + relative_start + SHEETPATH_PREFIX.len();
        let value_end = normalized[value_start..]
            .find('"')
            .map(|offset| value_start + offset)
            .ok_or_else(|| "Atopile netlist has an unterminated sheetpath name".to_string())?;
        canonical.push_str(&normalized[cursor..value_start]);
        let sheetpath = normalized[value_start..value_end].replace('\\', "/");
        let source_relative = if let Some(marker) = sheetpath.rfind(SOURCE_MARKER) {
            &sheetpath[marker + 1..]
        } else if sheetpath.starts_with("elec/src/") {
            sheetpath.as_str()
        } else {
            return Err(format!(
                "Atopile sheetpath is not rooted at elec/src: {sheetpath}"
            ));
        };
        canonical.push_str(source_relative);
        cursor = value_end;
        sheetpath_count += 1;
    }
    if sheetpath_count == 0 {
        return Err("Atopile netlist has no sheetpath identities".into());
    }
    canonical.push_str(&normalized[cursor..]);
    Ok(crate::sha256(canonical.as_bytes()))
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
    for (trace_ordinal, trace) in board.trace_items.iter().enumerate() {
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
                        "segment:{trace_ordinal}:{net_number}:{layer}:{:.6}:{:.6}:{:.6}:{:.6}:{:.6}",
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
                        "via:{trace_ordinal}:{net_number}:{}:{:.6}:{:.6}:{:.6}:{:.6}",
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
    let mut pad_occurrences = BTreeMap::new();
    for footprint in &board.footprints {
        let reference = footprint_reference(footprint).unwrap_or("");
        for pad in &footprint.pads {
            let Some((net_number, net_name)) = &pad.net else {
                continue;
            };
            let point = pad_world_position(footprint, pad);
            let pad_id = format!("{reference}.{}", pad.number);
            if net_number.as_f64() as i64 == 41 {
                if !net41_pad_ids.insert(pad_id.clone()) {
                    return Err(format!(
                        "production net 41 duplicated pad identity {pad_id}"
                    ));
                }
                net41_pad_positions.insert(pad_id.clone(), point);
                adjacency.entry(point_key(point)).or_default();
            }
            if selv_nets.contains(net_name.as_str()) {
                let occurrence = pad_occurrences
                    .entry((reference.to_string(), pad.number.clone()))
                    .and_modify(|value| *value += 1)
                    .or_insert(1usize);
                selv_pads.insert(format!(
                    "pad:{pad_id}#{occurrence}:{net_name}:{:.6}:{:.6}:{}",
                    point[0],
                    point[1],
                    pad.layers.join("/")
                ));
            }
        }
    }
    let mut selv_zones = BTreeSet::new();
    let mut net41_zone_count = 0;
    for (zone_ordinal, zone) in board.zones.iter().enumerate() {
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
                "zone:{zone_ordinal}:{}:{}:{}",
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

fn exact_strings(value: &Value, pointer: &str, expected: &[&str]) -> Result<(), String> {
    let rows = array(value, pointer)?;
    if rows.len() != expected.len()
        || rows
            .iter()
            .zip(expected)
            .any(|(actual, expected)| actual.as_str() != Some(*expected))
    {
        return Err(format!("{pointer} changed or is out of order"));
    }
    Ok(())
}

fn f64_array(value: &Value, pointer: &str) -> Result<Vec<f64>, String> {
    array(value, pointer)?
        .iter()
        .map(|item| {
            item.as_f64()
                .filter(|number| number.is_finite())
                .ok_or_else(|| format!("{pointer} must contain finite numbers"))
        })
        .collect()
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

fn validate_design_basis_contract(
    basis: &Value,
    manifest_sha256: &str,
    receipt_sha256: &str,
) -> Result<(), String> {
    if string(basis, "/predecessor/manifest_sha256")? != manifest_sha256
        || string(basis, "/predecessor/receipt_sha256")? != receipt_sha256
        || string(basis, "/predecessor/status")? != "stopped-indeterminate"
        || string(basis, "/predecessor/placement_selector")?
            != "one row per predecessor_placement_id at east_shift_mm == 4.0"
        || usize_at(basis, "/predecessor/placement_count")? != 60
        || usize_at(basis, "/predecessor/revalidated_count")? != 60
    {
        return Err("design basis has stale or incomplete predecessor authority".into());
    }
    exact_strings(
        basis,
        "/fixed_copper_categories",
        &[
            "all non-net-41 pads",
            "all non-net-41 tracks",
            "all non-net-41 vias",
            "all zones",
        ],
    )?;
    exact_strings(
        basis,
        "/authority_roles",
        &[
            "clearance.hv_lv.project.target",
            "creepage.hv_lv.pd3.production",
        ],
    )?;
    if basis.pointer("/current_capacity/width_mm") != Some(&json!(0.5))
        || string(basis, "/current_capacity/copper_layer")? != "In3.Cu"
        || basis.pointer("/current_capacity/via_diameter_mm") != Some(&json!(0.9))
        || basis.pointer("/current_capacity/via_drill_mm") != Some(&json!(0.3))
        || usize_at(basis, "/necessary_bound/placement_template_pairs")? != 720
        || usize_at(basis, "/necessary_bound/selv_pads_per_placement")? != 19
        || string(basis, "/necessary_bound/method")?
            != "Rust pad-to-capsule distance over every LV_CONTROL pad intersecting In3.Cu/all-copper for all 60 predecessor placements and all 12 corridor/portal templates at the admitted 122.64 mm endpoint column"
        || basis.pointer("/necessary_bound/minimum_straight_line_selv_gap_mm") != Some(&json!(12.9))
        || basis.pointer("/necessary_bound/maximum_straight_line_selv_gap_mm") != Some(&json!(15.4))
        || basis.pointer("/necessary_bound/required_clearance_mm") != Some(&json!(6.0))
        || basis.pointer("/necessary_bound/required_creepage_mm") != Some(&json!(12.6))
        || usize_at(basis, "/necessary_bound/potentially_feasible_pairs")? != 720
        || basis.pointer("/necessary_bound/admitted_endpoint_x_mm") != Some(&json!([122.64]))
        || usize_at(
            basis,
            "/necessary_bound/unbounded_candidates_requiring_full_screening",
        )? != 2160
        || string(basis, "/necessary_bound/closest_relationship")?
            != "J1.1 to the vertical corridor segment"
        || string(basis, "/necessary_bound/interpretation")?
            != "A surface path cannot be shorter than its straight-line endpoint separation, so this necessary bound proves one complete 720-candidate endpoint column remains eligible and satisfies the plan's at-least-one-template admission rule. It does not claim the other 2,160 candidates pass this bound; every candidate requires the full scratch screen, and this is not a routed-board safety verdict."
    {
        return Err("design basis weakened its capacity or necessary-bound contract".into());
    }
    exact_strings(
        basis,
        "/limitations",
        &[
            "Current-edition IEC 60335-1 and IEC 60335-2-6 review remains required.",
            "The bound is an admission test; every materialized survivor still requires complete SELV, mechanics, connectivity, containment, and KiCad DRC vetoes.",
            "No enclosure, connector access, new via span, layer change, or manufacturing-slot authority is granted.",
            "The production predecessor is disconnected at C7.1; this campaign replaces the full route from C7.1 and must prove connectivity before any promotion.",
        ],
    )?;
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

pub struct DeclarationInputs<'a> {
    pub declaration_json: &'a str,
    pub basis_json: &'a str,
    pub board_text: &'a str,
    pub predecessor_receipt_json: &'a str,
    pub predecessor_manifest_json: &'a str,
    pub domain_manifest_text: &'a str,
    pub netlist_text: &'a str,
    pub kicad_dru_text: &'a str,
    pub candidate_set_json: &'a str,
}

pub fn validate_declaration(inputs: &DeclarationInputs<'_>) -> Result<Value, String> {
    let declaration: Value = serde_json::from_str(inputs.declaration_json)
        .map_err(|error| format!("invalid declaration JSON: {error}"))?;
    let basis: Value = serde_json::from_str(inputs.basis_json)
        .map_err(|error| format!("invalid design-basis JSON: {error}"))?;
    let predecessor_receipt: Value = serde_json::from_str(inputs.predecessor_receipt_json)
        .map_err(|error| format!("invalid predecessor receipt JSON: {error}"))?;
    let predecessor_manifest: Value = serde_json::from_str(inputs.predecessor_manifest_json)
        .map_err(|error| format!("invalid predecessor manifest JSON: {error}"))?;
    let candidate_set: Value = serde_json::from_str(inputs.candidate_set_json)
        .map_err(|error| format!("invalid candidate-set JSON: {error}"))?;

    if string(&declaration, "/schema_version")? != DECLARATION_SCHEMA
        || string(&declaration, "/status")? != "declared"
        || string(&basis, "/schema_version")? != BASIS_SCHEMA
        || string(&basis, "/status")? != "authorized"
        || string(&basis, "/author_role")? != "pcb-designer"
    {
        return Err("unsupported declaration, lifecycle status, or design-basis schema".into());
    }
    if string(&predecessor_receipt, "/status")? != "stopped-indeterminate"
        || string(&declaration, "/predecessor/relation")? != "new-design-hypothesis"
        || string(&declaration, "/predecessor/accepted_status")? != "stopped-indeterminate"
        || declaration
            .pointer("/predecessor/exhaustion_claimed")
            .and_then(Value::as_bool)
            != Some(false)
    {
        return Err("predecessor does not authorize this non-exhaustive successor family".into());
    }

    let board_sha256 = crate::sha256(inputs.board_text.as_bytes());
    let basis_sha256 = crate::sha256(inputs.basis_json.as_bytes());
    let receipt_sha256 = crate::sha256(inputs.predecessor_receipt_json.as_bytes());
    let manifest_sha256 = crate::sha256(inputs.predecessor_manifest_json.as_bytes());
    let domain_sha256 = crate::sha256(inputs.domain_manifest_text.as_bytes());
    let netlist_sha256 = netlist_identity_sha256(inputs.netlist_text)?;
    let kicad_dru_sha256 = crate::sha256(inputs.kicad_dru_text.as_bytes());
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
    validate_design_basis_contract(&basis, &manifest_sha256, &receipt_sha256)?;
    let live_authority = crate::safety_value_authority::authority_contract()?;
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
    let topology = board_topology_snapshot(inputs.board_text, inputs.domain_manifest_text)?;
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
    exact_strings(
        &declaration,
        "/family/ordering",
        &[
            "predecessor_placement_id",
            "endpoint_x_mm",
            "corridor_x_mm",
            "entry_y_mm",
        ],
    )?;
    if string(&declaration, "/family/placement_selector")?
        != "one row per predecessor_placement_id at east_shift_mm == 4.0"
    {
        return Err("corridor family changed its predecessor selector".into());
    }
    exact_strings(
        &declaration,
        "/screening/hard_vetoes",
        &[
            "clearance",
            "creepage",
            "complete_selv_denominator",
            "new_safety_signature",
            "worsened_safety_signature",
            "connectivity",
            "containment",
            "body_overlap",
            "courtyard_overlap",
            "drc_cap",
            "drc_hard_rule",
        ],
    )?;
    exact_strings(
        &declaration,
        "/screening/ranking",
        &[
            "descending minimum(clearance_margin, creepage_margin)",
            "descending clearance",
            "descending creepage",
            "ascending route_length",
            "ascending canonical_candidate_id",
        ],
    )?;
    if usize_at(&declaration, "/screening/route_first_survivors")? != 12
        || usize_at(&declaration, "/screening/promotion_budget")? != 1
        || declaration
            .pointer("/screening/retain_raw_measurements")
            .and_then(Value::as_bool)
            != Some(true)
        || declaration
            .pointer("/screening/require_role_value_source_attribution")
            .and_then(Value::as_bool)
            != Some(true)
        || declaration
            .pointer("/selv_denominator/empty_is_error")
            .and_then(Value::as_bool)
            != Some(true)
    {
        return Err("corridor screening policy is incomplete or weakened".into());
    }
    if usize_at(&declaration, "/route/net_index")? != 41
        || string(&declaration, "/route/net_name")? != "discharge.r_snub1-p2"
        || declaration.pointer("/route/existing_endpoints") != Some(&json!(["C7.1", "R14.2"]))
        || string(&declaration, "/route/existing_via/type")? != "blind"
        || declaration.pointer("/route/existing_via/diameter_mm") != Some(&json!(0.9))
        || declaration.pointer("/route/existing_via/drill_mm") != Some(&json!(0.3))
        || declaration.pointer("/route/existing_via/span") != Some(&json!(["In3.Cu", "F.Cu"]))
        || usize_at(&declaration, "/route/existing_zone_count")? != 0
    {
        return Err("net-41 route identity or current-capacity policy changed".into());
    }
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
    for line in inputs.board_text.lines() {
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

    let selected_rows = predecessor_manifest
        .pointer("/results")
        .and_then(Value::as_array)
        .ok_or_else(|| "predecessor manifest has no results".to_string())?;
    let mut placements = BTreeMap::new();
    for row in selected_rows
        .iter()
        .filter(|row| row.pointer("/east_shift_mm").and_then(Value::as_f64) == Some(4.0))
    {
        let placement_id = string(row, "/predecessor_placement_id")?;
        let j1 = f64_array(row, "/placements/J1")?;
        if j1.len() < 2
            || placements
                .insert(placement_id.to_string(), [j1[0], j1[1]])
                .is_some()
        {
            return Err("predecessor placement identities or J1 geometry are duplicated".into());
        }
    }
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
    let generated_hashes: Vec<_> = expected_generated_hashes.into_iter().collect();
    let generated_hash_values: Vec<_> = generated_hashes
        .iter()
        .map(|digest| json!(digest))
        .collect();
    if array(&candidate_set, "/generated_input_hashes")? != &generated_hash_values {
        return Err("candidate set generated-input identities are out of order".into());
    }
    let mut endpoint_x_mm = f64_array(&declaration, "/family/endpoint_x_mm")?;
    let mut corridor_x_mm = f64_array(&declaration, "/family/corridor_x_mm")?;
    let mut entry_y_mm = f64_array(&declaration, "/family/entry_y_mm")?;
    endpoint_x_mm.sort_by(f64::total_cmp);
    corridor_x_mm.sort_by(f64::total_cmp);
    entry_y_mm.sort_by(f64::total_cmp);
    let fixed_start: [f64; 2] = serde_json::from_value(
        declaration
            .pointer("/family/fixed_start")
            .cloned()
            .ok_or_else(|| "candidate family omitted fixed_start".to_string())?,
    )
    .map_err(|error| format!("invalid fixed_start: {error}"))?;
    let endpoint_y_mm = declaration
        .pointer("/family/endpoint_y_mm")
        .and_then(Value::as_f64)
        .ok_or_else(|| "candidate family omitted endpoint_y_mm".to_string())?;
    let knee_y_mm = declaration
        .pointer("/family/knee_y_mm")
        .and_then(Value::as_f64)
        .ok_or_else(|| "candidate family omitted knee_y_mm".to_string())?;
    let layer = string(&declaration, "/family/layer")?;
    let route_width_mm = declaration
        .pointer("/family/route_width_mm")
        .and_then(Value::as_f64)
        .ok_or_else(|| "candidate family omitted route_width_mm".to_string())?;
    let via_diameter_mm = declaration
        .pointer("/family/via_diameter_mm")
        .and_then(Value::as_f64)
        .ok_or_else(|| "candidate family omitted via_diameter_mm".to_string())?;
    let via_drill_mm = declaration
        .pointer("/family/via_drill_mm")
        .and_then(Value::as_f64)
        .ok_or_else(|| "candidate family omitted via_drill_mm".to_string())?;
    let via_span: [String; 2] = serde_json::from_value(
        declaration
            .pointer("/family/via_span")
            .cloned()
            .ok_or_else(|| "candidate family omitted via_span".to_string())?,
    )
    .map_err(|error| format!("invalid via_span: {error}"))?;
    let declaration_hash = string(&declaration, "/declaration_authority_digest")?;
    let board_hash = string(&declaration, "/production_board_sha256")?;
    let authority_hash = string(&declaration, "/topology_authority_digest")?;
    let mut expected_candidates = Vec::with_capacity(cardinality);
    for (placement_id, j1_position) in &placements {
        for endpoint_x in &endpoint_x_mm {
            for corridor_x in &corridor_x_mm {
                for entry_y in &entry_y_mm {
                    let route_points = vec![
                        fixed_start,
                        [*corridor_x, *entry_y],
                        [*corridor_x, knee_y_mm],
                        [*endpoint_x, endpoint_y_mm],
                    ];
                    let identity = (
                        declaration_hash,
                        board_hash,
                        &generated_hashes,
                        authority_hash,
                        placement_id,
                        j1_position,
                        endpoint_x,
                        corridor_x,
                        entry_y,
                        &route_points,
                        layer,
                        route_width_mm,
                        via_diameter_mm,
                        via_drill_mm,
                        &via_span,
                    );
                    let digest = candidate_digest(&identity)?;
                    expected_candidates.push(json!({
                        "ordinal": expected_candidates.len() + 1,
                        "candidate_id": format!("NET41-CORRIDOR-{digest}"),
                        "placement_id": placement_id,
                        "j1_position": j1_position,
                        "endpoint_x_mm": endpoint_x,
                        "corridor_x_mm": corridor_x,
                        "entry_y_mm": entry_y,
                        "route_points": route_points,
                    }));
                }
            }
        }
    }
    let candidate_rows = array(&candidate_set, "/candidates")?;
    if candidate_rows != &expected_candidates {
        return Err("candidate set does not exactly reconstruct from bound Rust authority".into());
    }
    let mut candidate_envelope = candidate_set.clone();
    candidate_envelope
        .as_object_mut()
        .ok_or_else(|| "candidate set must be an object".to_string())?
        .remove("candidate_set_digest");
    let candidate_set_digest = candidate_digest(&candidate_envelope)?;
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
#[pyo3(signature = (*, declaration_bytes, basis_bytes, board_bytes, predecessor_receipt_bytes, predecessor_manifest_bytes, domain_manifest_bytes, netlist_bytes, kicad_dru_bytes, candidate_set_bytes))]
#[allow(clippy::too_many_arguments)] // stable Python seam mirrors the nine bound evidence inputs
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
    let inputs = DeclarationInputs {
        declaration_json: decode(declaration_bytes)?,
        basis_json: decode(basis_bytes)?,
        board_text: decode(board_bytes)?,
        predecessor_receipt_json: decode(predecessor_receipt_bytes)?,
        predecessor_manifest_json: decode(predecessor_manifest_bytes)?,
        domain_manifest_text: decode(domain_manifest_bytes)?,
        netlist_text: decode(netlist_bytes)?,
        kicad_dru_text: decode(kicad_dru_bytes)?,
        candidate_set_json: decode(candidate_set_bytes)?,
    };
    validate_declaration(&inputs)
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
    fn netlist_identity_ignores_checkout_root_but_not_source_identity() {
        let local = "(export\r\n  (sheetpath (names \"/home/dev/worktree/elec/src/main.ato:Top::C1\") (tstamps \"a\"))\r\n)";
        let ci = "(export\n  (sheetpath (names \"/__w/temper/temper/elec/src/main.ato:Top::C1\") (tstamps \"a\"))\n)";
        let changed = "(export\n  (sheetpath (names \"/__w/temper/temper/elec/src/main.ato:Top::C2\") (tstamps \"a\"))\n)";

        assert_eq!(
            netlist_identity_sha256(local).unwrap(),
            netlist_identity_sha256(ci).unwrap()
        );
        assert_ne!(
            netlist_identity_sha256(ci).unwrap(),
            netlist_identity_sha256(changed).unwrap()
        );
        assert!(netlist_identity_sha256("(export)").is_err());
    }

    #[cfg_attr(test, test)]
    fn necessary_bound_cannot_be_inflated_after_repinning() {
        let mut basis: Value = serde_json::from_str(include_str!(
            "../../../docs/evidence/net41-route-layer-corridor-20260831/design-basis.json"
        ))
        .expect("committed design basis is valid JSON");
        let manifest_sha256 = string(&basis, "/predecessor/manifest_sha256")
            .expect("basis binds predecessor manifest")
            .to_string();
        let receipt_sha256 = string(&basis, "/predecessor/receipt_sha256")
            .expect("basis binds predecessor receipt")
            .to_string();
        assert!(validate_design_basis_contract(&basis, &manifest_sha256, &receipt_sha256).is_ok());
        basis["necessary_bound"]["minimum_straight_line_selv_gap_mm"] = json!(99.0);
        assert!(validate_design_basis_contract(&basis, &manifest_sha256, &receipt_sha256).is_err());
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
        ("regional_topology::tests::netlist_identity_ignores_checkout_root_but_not_source_identity", netlist_identity_ignores_checkout_root_but_not_source_identity),
        ("regional_topology::tests::necessary_bound_cannot_be_inflated_after_repinning", necessary_bound_cannot_be_inflated_after_repinning),
        ("regional_topology::tests::production_authorization_is_always_denied", production_authorization_is_always_denied),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}
