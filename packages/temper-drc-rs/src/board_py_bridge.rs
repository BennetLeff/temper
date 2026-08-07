// PyO3 bridge helpers: extract typed values from Python dicts.
//
// Common extractors (`extract_str`, `extract_opt_str`, `extract_f64`,
// `extract_opt_f64`, `extract_opt_bool`, `extract_str_list`,
// `extract_dict_list`) are delegated to the shared `temper_py_bridge`
// crate's `DictExtract` trait — the semantics (error messages, defaults,
// None-handling) are byte-for-byte identical. Crate-specific extractors
// (`extract_i32`, `extract_point`, `extract_component`, etc.) remain local.
//
// Origin: U2 of docs/plans/2026-06-30-003-feat-temper-drc-rs-engine-plan.md

use std::collections::HashMap;

use geo::{Line, Point, Polygon};
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::{PyAny, PyDict, PyList};
use temper_py_bridge::DictExtract;

use crate::board::{
    BoardSide, BoardState, Component, ComponentRef, CopperZone, Net, NetClassRules, NetClassName,
    NetName, PackageType, TraceSegment, Via,
};

// ---------------------------------------------------------------------------
// Primitive extractors
// ---------------------------------------------------------------------------
//
// `extract_str`, `extract_opt_str`, `extract_f64`, `extract_opt_f64`,
// `extract_opt_bool`, `extract_str_list`, and `extract_dict_list` are
// provided by the `temper_py_bridge::DictExtract` trait (imported above).
// Call sites use `dict.extract_str("key")` etc. directly on a
// `Bound<'_, PyDict>`.
//
// `extract_i32` has no equivalent in the shared trait (the shared crate
// only provides f64/str/bool extractors), so it stays local.

/// Extract a required i32 value from a dict.
pub fn extract_i32(dict: &Bound<'_, PyDict>, key: &str, default: i32) -> PyResult<i32> {
    match dict.get_item(key)? {
        Some(val) if !val.is_none() => {
            val.extract::<i32>().map_err(|e| {
                PyValueError::new_err(format!("key '{key}' is not an integer: {e}"))
            })
        }
        _ => Ok(default),
    }
}

// ---------------------------------------------------------------------------
// Geometry extractors
// ---------------------------------------------------------------------------

/// Extract a geo::Point from a dict containing "x" and "y" keys.
pub fn extract_point(dict: &Bound<'_, PyDict>, key: &str) -> PyResult<Point<f64>> {
    let item = dict
        .get_item(key)?
        .ok_or_else(|| PyValueError::new_err(format!("missing required key: {key}")))?;
    let inner: Bound<'_, PyDict> = item
        .cast_into::<PyDict>()
        .map_err(|e| PyValueError::new_err(format!("key '{key}' is not a dict: {e}")))?;
    let x = inner.extract_f64("x", 0.0)?;
    let y = inner.extract_f64("y", 0.0)?;
    Ok(Point::new(x, y))
}

/// Extract an optional geo::Point from a dict.
pub fn extract_opt_point(dict: &Bound<'_, PyDict>, key: &str) -> PyResult<Option<Point<f64>>> {
    match dict.get_item(key)? {
        Some(val) if !val.is_none() => {
            if let Ok(inner) = val.cast_into::<PyDict>() {
                let x = inner.extract_f64("x", 0.0)?;
                let y = inner.extract_f64("y", 0.0)?;
                return Ok(Some(Point::new(x, y)));
            }
        }
        _ => {}
    }
    Ok(None)
}

/// Parse a geo::Polygon from a Python list of coordinate pairs.
///
/// The value should be a list of [x, y] pairs forming the polygon exterior
/// ring (assumed closed — first point need not equal last point; the
/// polygon is auto-closed).
fn polygon_from_value(val: &Bound<'_, PyAny>, key: &str) -> PyResult<Polygon<f64>> {
    let list: Bound<'_, PyList> = val.clone().cast_into::<PyList>().map_err(|e| {
        PyValueError::new_err(format!("key '{key}' is not a list: {e}"))
    })?;

    let coords: Vec<(f64, f64)> = list
        .iter()
        .map(|item| -> PyResult<(f64, f64)> {
            let pair: Bound<'_, PyList> = item.cast_into::<PyList>().map_err(|e| {
                PyValueError::new_err(format!(
                    "coordinate in '{key}' polygon is not a list of 2 numbers: {e}"
                ))
            })?;
            if pair.len() < 2 {
                return Err(PyValueError::new_err(format!(
                    "coordinate in '{key}' polygon has fewer than 2 elements"
                )));
            }
            let x: f64 = pair.get_item(0)?.extract().map_err(|e| {
                PyValueError::new_err(format!("x coordinate in '{key}' polygon: {e}"))
            })?;
            let y: f64 = pair.get_item(1)?.extract().map_err(|e| {
                PyValueError::new_err(format!("y coordinate in '{key}' polygon: {e}"))
            })?;
            Ok((x, y))
        })
        .collect::<Result<Vec<_>, _>>()?;

    if coords.is_empty() {
        return Err(PyValueError::new_err(format!(
            "polygon '{key}' has no coordinates"
        )));
    }

    let exterior: Vec<geo::Coord<f64>> = coords.iter().map(|&(x, y)| geo::Coord { x, y }).collect();
    let polygon = Polygon::new(geo::LineString::new(exterior), Vec::new());
    Ok(polygon)
}

/// Extract a geo::Polygon from a dict value.
pub fn extract_polygon(dict: &Bound<'_, PyDict>, key: &str) -> PyResult<Polygon<f64>> {
    let val = dict
        .get_item(key)?
        .ok_or_else(|| PyValueError::new_err(format!("missing required key: {key}")))?;
    polygon_from_value(&val, key)
}

/// Extract an optional polygon.
pub fn extract_opt_polygon(
    dict: &Bound<'_, PyDict>,
    key: &str,
) -> PyResult<Option<Polygon<f64>>> {
    match dict.get_item(key)? {
        Some(val) if !val.is_none() => polygon_from_value(&val, key).map(Some),
        _ => Ok(None),
    }
}

// ---------------------------------------------------------------------------
// Component extraction helpers
// ---------------------------------------------------------------------------

fn parse_board_side(s: &str) -> PyResult<BoardSide> {
    match s.to_lowercase().as_str() {
        "top" => Ok(BoardSide::Top),
        "bottom" => Ok(BoardSide::Bottom),
        other => Err(PyValueError::new_err(format!(
            "invalid BoardSide: '{other}'. Expected 'top' or 'bottom'"
        ))),
    }
}

fn parse_package_type(s: &str) -> PyResult<PackageType> {
    match s.to_lowercase().as_str() {
        "smd" => Ok(PackageType::Smd),
        "tht" => Ok(PackageType::Tht),
        "qfn" => Ok(PackageType::Qfn),
        "qfp" => Ok(PackageType::Qfp),
        "bga" => Ok(PackageType::Bga),
        "dpak" => Ok(PackageType::Dpak),
        "to247" | "to-247" => Ok(PackageType::To247),
        "to220" | "to-220" => Ok(PackageType::To220),
        _ => Ok(PackageType::Other),
    }
}

fn extract_component(dict: &Bound<'_, PyDict>) -> PyResult<Component> {
    let refdes = dict.extract_str("ref")?;
    let x = dict.extract_f64("x", 0.0)?;
    let y = dict.extract_f64("y", 0.0)?;
    let rotation = dict.extract_f64("rot", 0.0)?;
    let side_str = dict.extract_str("side")?;
    let side = parse_board_side(&side_str)?;
    let width = dict.extract_f64("width", 0.0)?;
    let height = dict.extract_f64("height", 0.0)?;
    let net_class = dict.extract_str("net_class")?;
    let power_dissipation_w = dict.extract_opt_f64("power_dissipation_w")?;
    let package_type_str = dict.extract_str("package_type")?;
    let package_type = parse_package_type(&package_type_str)?;
    let is_magnetic = dict.extract_opt_bool("is_magnetic")?.unwrap_or(false);
    let is_electrolytic = dict.extract_opt_bool("is_electrolytic")?.unwrap_or(false);
    let vent_direction = dict.extract_opt_f64("vent_direction")?;
    let footprint_polygon = extract_opt_polygon(dict, "footprint_polygon")?;

    Ok(Component {
        refdes: ComponentRef(refdes),
        center: Point::new(x, y),
        rotation,
        side,
        width,
        height,
        net_class: NetClassName(net_class),
        power_dissipation_w,
        package_type,
        is_magnetic,
        is_electrolytic,
        vent_direction,
        footprint_polygon,
    })
}

// ---------------------------------------------------------------------------
// NetClassRules extraction
// ---------------------------------------------------------------------------

fn extract_net_class_rules(dict: &Bound<'_, PyDict>) -> PyResult<NetClassRules> {
    Ok(NetClassRules {
        name: dict.extract_str("name").unwrap_or_default(),
        trace_width_mm: dict.extract_f64("trace_width_mm", 0.2)?,
        clearance_mm: dict.extract_f64("clearance_mm", 0.2)?,
        dru_priority: dict.extract_f64("dru_priority", 0.0)?.round() as i32,
        via_diameter: dict.extract_f64("via_diameter", 0.6)?,
        via_drill: dict.extract_f64("via_drill", 0.3)?,
        via_template: dict.extract_opt_str("via_template")?,
        creepage_mm: dict.extract_f64("creepage_mm", 0.0)?,
        voltage_v: dict.extract_f64("voltage_v", 0.0)?,
        target_impedance: dict.extract_opt_f64("target_impedance")?,
        max_current_rating: dict.extract_opt_f64("max_current_rating")?,
        required_layer: dict.extract_opt_str("required_layer")?,
        layer: dict.extract_opt_str("layer")?,
        safety_category: dict.extract_opt_str("safety_category")?,
        routing_strategy: dict.extract_opt_str("routing_strategy")?,
        ..NetClassRules::default()
    })
}

// ---------------------------------------------------------------------------
// Trace extraction
// ---------------------------------------------------------------------------

/// Extract a list of f64 numbers from a list value.
fn extract_f64_list(val: &Bound<'_, PyAny>) -> PyResult<Vec<f64>> {
    let list: Bound<'_, PyList> = val.clone().cast_into::<PyList>().map_err(|e| {
        PyValueError::new_err(format!("value is not a list: {e}"))
    })?;
    list.iter()
        .map(|item| -> PyResult<f64> {
            item.extract().map_err(|e| {
                PyValueError::new_err(format!("list element is not a number: {e}"))
            })
        })
        .collect()
}

fn extract_trace_segment(dict: &Bound<'_, PyDict>) -> PyResult<TraceSegment> {
    let net = dict.extract_str("net")?;
    let layer = dict.extract_str("layer")?;
    let width = dict.extract_f64("width", 0.2)?;

    // Segments from Python: [[x1, y1, x2, y2], [x1, y1, x2, y2], ...]
    let mut segments = Vec::new();
    if let Some(segments_val) = dict.get_item("segments")?
        && let Ok(seg_list) = segments_val.cast_into::<PyList>()
    {
        for item in seg_list.iter() {
            let coords = extract_f64_list(&item)?;
            if coords.len() >= 4 {
                segments.push(Line::new(
                    Point::new(coords[0], coords[1]),
                    Point::new(coords[2], coords[3]),
                ));
            }
        }
    }

    Ok(TraceSegment {
        net: NetName(net),
        layer,
        width,
        segments,
    })
}

// ---------------------------------------------------------------------------
// Via extraction
// ---------------------------------------------------------------------------

fn extract_via(dict: &Bound<'_, PyDict>) -> PyResult<Via> {
    let net = dict.extract_str("net")?;
    let x = dict.extract_f64("x", 0.0)?;
    let y = dict.extract_f64("y", 0.0)?;
    let drill = dict.extract_f64("drill", 0.3)?;
    let pad = dict.extract_f64("pad", 0.6)?;
    let from_layer = dict.extract_opt_str("from_layer")?.unwrap_or_else(|| "F.Cu".into());
    let to_layer = dict.extract_opt_str("to_layer")?.unwrap_or_else(|| "B.Cu".into());

    Ok(Via {
        net: NetName(net),
        position: Point::new(x, y),
        drill,
        pad,
        from_layer,
        to_layer,
    })
}

// ---------------------------------------------------------------------------
// CopperZone extraction
// ---------------------------------------------------------------------------

fn extract_copper_zone(dict: &Bound<'_, PyDict>) -> PyResult<CopperZone> {
    let net = dict.extract_str("net")?;
    let layer = dict.extract_str("layer")?;
    let polygon = extract_polygon(dict, "polygon")?;

    Ok(CopperZone {
        net: NetName(net),
        layer,
        polygon,
    })
}

// ---------------------------------------------------------------------------
// Composite dict parsers (orchestrated by build_board_state)
// ---------------------------------------------------------------------------

/// Parse `board_dict["nets"]` preserving the dict's iteration order.
///
/// Returns an ordered `Vec<(net_name, component_refs)>`, NOT a `HashMap`.
/// `PyDict::iter()` already yields items in the dict's insertion order
/// (matching whatever order the Python producer built `nets` in — see
/// `build_board_state`'s doc comment). A `HashMap` intermediate here would
/// throw that order away: Rust's default `RandomState` hasher reseeds per
/// process, so `HashMap::into_iter()` order is stable within one process
/// but differs across processes, which previously made the `nets` field of
/// the serialized `BoardState` (see `serialize_board_state` in `lib.rs`)
/// nondeterministic across runs even for byte-identical input — breaking
/// content-addressed hashing of the JSON (goal-set R5). Cross-process
/// regression test:
/// `packages/temper-placer/tests/validation/test_drc_board_bridge_nets_order_determinism.py`.
fn parse_nets_from_dict(
    board_dict: &Bound<'_, PyDict>,
) -> PyResult<Vec<(String, Vec<String>)>> {
    let mut result = Vec::new();
    if let Some(nets_val) = board_dict.get_item("nets")?
        && let Ok(nets_dict) = nets_val.cast_into::<PyDict>()
    {
        for (key, val) in nets_dict.iter() {
            let net_name: String = key.extract().map_err(|e| {
                PyValueError::new_err(format!("nets key is not a string: {e}"))
            })?;
            let list: Bound<'_, PyList> = val.cast_into::<PyList>().map_err(|e| {
                PyValueError::new_err(format!("nets['{net_name}'] is not a list: {e}"))
            })?;
            let comps: Vec<String> = list
                .iter()
                .map(|item| {
                    item.extract::<String>().map_err(|e| {
                        PyValueError::new_err(format!(
                            "component ref in nets['{net_name}'] is not a string: {e}"
                        ))
                    })
                })
                .collect::<Result<Vec<_>, _>>()?;
            result.push((net_name, comps));
        }
    }
    Ok(result)
}

fn parse_net_classes_from_dict(
    board_dict: &Bound<'_, PyDict>,
) -> PyResult<HashMap<String, String>> {
    let mut result = HashMap::new();
    if let Some(nc_val) = board_dict.get_item("net_classes")?
        && let Ok(nc_dict) = nc_val.cast_into::<PyDict>()
    {
        for (key, val) in nc_dict.iter() {
            let net_name: String = key.extract().map_err(|e| {
                PyValueError::new_err(format!("net_classes key is not a string: {e}"))
            })?;
            let class_name: String = val.extract().map_err(|e| {
                PyValueError::new_err(format!(
                    "net_classes['{net_name}'] is not a string: {e}"
                ))
            })?;
            result.insert(net_name, class_name);
        }
    }
    Ok(result)
}

fn parse_net_class_rules_from_dict(
    board_dict: &Bound<'_, PyDict>,
) -> PyResult<HashMap<NetClassName, NetClassRules>> {
    let mut result = HashMap::new();
    if let Some(ncr_val) = board_dict.get_item("net_class_rules")?
        && let Ok(ncr_dict) = ncr_val.cast_into::<PyDict>()
    {
        for (key, val) in ncr_dict.iter() {
            let class_name: String = key.extract().map_err(|e| {
                PyValueError::new_err(format!("net_class_rules key is not a string: {e}"))
            })?;
            let rules_dict: Bound<'_, PyDict> = val.cast_into::<PyDict>().map_err(|e| {
                PyValueError::new_err(format!(
                    "net_class_rules['{class_name}'] is not a dict: {e}"
                ))
            })?;
            result.insert(NetClassName(class_name), extract_net_class_rules(&rules_dict)?);
        }
    }
    Ok(result)
}

fn parse_traces_from_dict(board_dict: &Bound<'_, PyDict>) -> PyResult<Vec<TraceSegment>> {
    let trace_list = board_dict.extract_dict_list("traces")?;
    let mut result = Vec::with_capacity(trace_list.len());
    for trace_dict in trace_list {
        result.push(extract_trace_segment(&trace_dict)?);
    }
    Ok(result)
}

fn parse_zones_from_dict(board_dict: &Bound<'_, PyDict>) -> PyResult<Vec<CopperZone>> {
    let zone_list = board_dict.extract_dict_list("zones")?;
    let mut result = Vec::with_capacity(zone_list.len());
    for zone_dict in zone_list {
        result.push(extract_copper_zone(&zone_dict)?);
    }
    Ok(result)
}

// ---------------------------------------------------------------------------
// BoardState builder
// ---------------------------------------------------------------------------

/// Build a `BoardState` from a Python dict matching the K1 schema.
///
/// Schema (see plan §K1):
/// ```text
/// {
///   "board": {"width_mm": f, "height_mm": f, "margin_mm": f},
///   "components": [{ref, x, y, rot, side, width, height, net_class, ...}],
///   "nets": {"net_name": ["comp1", "comp2", ...]},
///   "net_classes": {"net_name": "class_name"},
///   "net_class_rules": {"class_name": {trace_width_mm, clearance_mm, ...}},
///   "traces": [{net, layer, width, segments}],      // optional
///   "vias": [{net, x, y, drill, pad, ...}],         // optional
///   "zones": [{net, layer, polygon}],                // optional
/// }
/// ```
pub fn build_board_state(board_dict: &Bound<'_, PyDict>) -> PyResult<BoardState> {
    // --- Board dimensions ---
    let board_item = board_dict
        .get_item("board")?
        .ok_or_else(|| PyValueError::new_err("missing required key: board"))?;
    let board_info: Bound<'_, PyDict> = board_item
        .cast_into::<PyDict>()
        .map_err(|e| PyValueError::new_err(format!("key 'board' is not a dict: {e}")))?;

    let width_mm = board_info.extract_f64("width_mm", 100.0)?;
    let height_mm = board_info.extract_f64("height_mm", 150.0)?;
    let margin_mm = board_info.extract_f64("margin_mm", 3.0)?;

    // --- Components ---
    let (electrical_components, mechanical_components) = {
        let comp_list = board_dict.extract_dict_list("components")?;
        let mut elec = Vec::with_capacity(comp_list.len());
        let mut mech = Vec::new();
        for comp_dict in comp_list {
            let is_mechanical = comp_dict.extract_opt_bool("is_mechanical")?.unwrap_or(false);
            let comp = extract_component(&comp_dict)?;
            if is_mechanical {
                mech.push(comp);
            } else {
                elec.push(comp);
            }
        }
        (elec, mech)
    };

    // --- Nets (order-preserving: [(net_name, [component_refs]), ...]) ---
    // Deliberately NOT a HashMap — see parse_nets_from_dict's doc comment.
    // The `.into_iter()` below must walk this Vec, not a HashMap, so the
    // resulting `nets: Vec<Net>` order matches the input dict's order.
    let nets_dict_raw = parse_nets_from_dict(board_dict)?;

    // --- Net classes (HashMap: net_name → class_name) ---
    let net_classes_raw = parse_net_classes_from_dict(board_dict)?;

    // --- Net class rules (HashMap: class_name → rules) ---
    let net_class_rules = parse_net_class_rules_from_dict(board_dict)?;

    // --- Join nets + net_classes + rules into Vec<Net> ---
    let nets: Vec<Net> = nets_dict_raw
        .into_iter()
        .map(|(name, comps)| {
            let net_name = NetName(name.clone());
            let class_name = net_classes_raw
                .get(&name)
                .map(|c| NetClassName(c.clone()))
                .unwrap_or(NetClassName("Unknown".to_string()));
            let rules = net_class_rules
                .get(&class_name)
                .cloned()
                .unwrap_or_else(|| NetClassRules {
                    trace_width_mm: 0.2,
                    clearance_mm: 0.2,
                    ..NetClassRules::default()
                });
            Net {
                name: net_name,
                components: comps.into_iter().map(ComponentRef).collect(),
                class: class_name,
                rules,
            }
        })
        .collect();

    // --- Traces (optional) ---
    let traces = parse_traces_from_dict(board_dict)?;

    // --- Vias (optional) ---
    let vias = {
        let via_list = board_dict.extract_dict_list("vias")?;
        let mut result = Vec::with_capacity(via_list.len());
        for via_dict in via_list {
            result.push(extract_via(&via_dict)?);
        }
        result
    };

    // --- Zones (optional) ---
    let zones = parse_zones_from_dict(board_dict)?;

    Ok(BoardState {
        width_mm,
        height_mm,
        margin_mm,
        electrical_components,
        mechanical_components,
        nets,
        net_class_rules,
        traces,
        vias,
        zones,
    })
}
