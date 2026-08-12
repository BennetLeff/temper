// PyO3 bridge helpers: extract typed values from Python dicts.
//
// Follows the `HashMapResolver` pattern from
// `packages/temper-constraint-compiler/src/pyo3_bridge.rs`.
//
// All extraction functions produce descriptive PyValueError messages
// on type mismatch or missing required keys.
//
// Origin: U2 of docs/plans/2026-06-30-003-feat-temper-drc-rs-engine-plan.md

use std::collections::{BTreeMap, HashMap};

use geo::{Line, Point, Polygon};
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::{PyAny, PyDict, PyList};

use crate::board::{
    BoardSide, BoardState, Component, ComponentRef, CopperZone, Net, NetClassRules, NetClassName,
    NetName, PackageType, TraceSegment, Via,
};

// ---------------------------------------------------------------------------
// Primitive extractors
// ---------------------------------------------------------------------------

/// Extract a required string value from a dict.
pub fn extract_str(dict: &Bound<'_, PyDict>, key: &str) -> PyResult<String> {
    dict.get_item(key)?
        .ok_or_else(|| PyValueError::new_err(format!("missing required key: {key}")))?
        .extract::<String>()
        .map_err(|e| {
            PyValueError::new_err(format!("key '{key}' is not a string: {e}"))
        })
}

/// Extract an optional string value from a dict (None if absent or null).
pub fn extract_opt_str(dict: &Bound<'_, PyDict>, key: &str) -> PyResult<Option<String>> {
    match dict.get_item(key)? {
        Some(val) if !val.is_none() => Ok(Some(val.extract::<String>().map_err(|e| {
            PyValueError::new_err(format!("key '{key}' is not a string: {e}"))
        })?)),
        _ => Ok(None),
    }
}

/// Extract a required f64 value from a dict.
pub fn extract_f64(dict: &Bound<'_, PyDict>, key: &str, default: f64) -> PyResult<f64> {
    match dict.get_item(key)? {
        Some(val) if !val.is_none() => {
            // Accept both float and int from Python
            val.extract::<f64>().map_err(|e| {
                PyValueError::new_err(format!("key '{key}' is not a number: {e}"))
            })
        }
        _ => Ok(default),
    }
}

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

/// Extract an optional f64 value from a dict.
pub fn extract_opt_f64(dict: &Bound<'_, PyDict>, key: &str) -> PyResult<Option<f64>> {
    match dict.get_item(key)? {
        Some(val) if !val.is_none() => {
            let v: f64 = val.extract().map_err(|e| {
                PyValueError::new_err(format!("key '{key}' is not a number: {e}"))
            })?;
            Ok(Some(v))
        }
        _ => Ok(None),
    }
}

/// Extract an optional bool value from a dict.
pub fn extract_opt_bool(dict: &Bound<'_, PyDict>, key: &str) -> PyResult<Option<bool>> {
    match dict.get_item(key)? {
        Some(val) if !val.is_none() => {
            let v: bool = val.extract().map_err(|e| {
                PyValueError::new_err(format!("key '{key}' is not a bool: {e}"))
            })?;
            Ok(Some(v))
        }
        _ => Ok(None),
    }
}

/// Extract a list of strings from a dict value.
pub fn extract_str_list(dict: &Bound<'_, PyDict>, key: &str) -> PyResult<Vec<String>> {
    match dict.get_item(key)? {
        Some(val) if !val.is_none() => {
            let list: Bound<'_, PyList> = val.cast_into::<PyList>().map_err(|e| {
                PyValueError::new_err(format!("key '{key}' is not a list: {e}"))
            })?;
            let mut result = Vec::with_capacity(list.len());
            for item in list.iter() {
                result.push(item.extract::<String>().map_err(|e| {
                    PyValueError::new_err(format!(
                        "item in '{key}' list is not a string: {e}"
                    ))
                })?);
            }
            Ok(result)
        }
        _ => Ok(Vec::new()),
    }
}

/// Extract a required list-of-dicts value.
pub fn extract_dict_list<'py>(
    dict: &Bound<'py, PyDict>,
    key: &str,
) -> PyResult<Vec<Bound<'py, PyDict>>> {
    match dict.get_item(key)? {
        Some(val) if !val.is_none() => {
            let list: Bound<'_, PyList> = val.cast_into::<PyList>().map_err(|e| {
                PyValueError::new_err(format!("key '{key}' is not a list: {e}"))
            })?;
            let mut result = Vec::with_capacity(list.len());
            for item in list.iter() {
                let d: Bound<'_, PyDict> = item.cast_into::<PyDict>().map_err(|e| {
                    PyValueError::new_err(format!(
                        "item in '{key}' list is not a dict: {e}"
                    ))
                })?;
                result.push(d);
            }
            Ok(result)
        }
        _ => Ok(Vec::new()),
    }
}

/// Reject any key in `dict` that is not in `known` — the hand-rolled
/// equivalent of serde's `#[serde(deny_unknown_fields)]` for the K1-schema
/// PyDict boundary, which is parsed by manual `get_item()` calls rather
/// than a `Deserialize` derive (so `deny_unknown_fields` itself does not
/// apply here). Without this, a misspelled or renamed key is not an
/// error: `extract_*` only ever reads keys it knows about, so anything
/// else in the dict is invisible — the exact silent-discard failure mode
/// that let `thermal_constraints` reach zero consumers for an unknown
/// period (docs/evidence/2026-08-08-drc-safety-rule-vacuity-audit.md) and
/// let the K1 "zones"/"traces"/"vias" key mismatches ship unnoticed.
/// Reports every unrecognized key at once (not just the first) so a
/// single bad payload surfaces its whole mismatch in one error.
pub fn reject_unknown_keys(
    dict: &Bound<'_, PyDict>,
    known: &[&str],
    context: &str,
) -> PyResult<()> {
    let mut unknown: Vec<String> = Vec::new();
    for key in dict.keys().iter() {
        let key_str: String = key.extract().map_err(|e| {
            PyValueError::new_err(format!("{context}: dict key is not a string: {e}"))
        })?;
        if !known.contains(&key_str.as_str()) {
            unknown.push(key_str);
        }
    }
    if !unknown.is_empty() {
        unknown.sort();
        let mut known_sorted: Vec<&str> = known.to_vec();
        known_sorted.sort_unstable();
        return Err(PyValueError::new_err(format!(
            "{context}: unrecognized key(s) {unknown:?} (expected a subset of {known_sorted:?})"
        )));
    }
    Ok(())
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
    let x = extract_f64(&inner, "x", 0.0)?;
    let y = extract_f64(&inner, "y", 0.0)?;
    Ok(Point::new(x, y))
}

/// Extract an optional geo::Point from a dict.
pub fn extract_opt_point(dict: &Bound<'_, PyDict>, key: &str) -> PyResult<Option<Point<f64>>> {
    match dict.get_item(key)? {
        Some(val) if !val.is_none() => {
            if let Ok(inner) = val.cast_into::<PyDict>() {
                let x = extract_f64(&inner, "x", 0.0)?;
                let y = extract_f64(&inner, "y", 0.0)?;
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

pub(crate) fn parse_board_side(s: &str) -> PyResult<BoardSide> {
    match s.to_lowercase().as_str() {
        "top" => Ok(BoardSide::Top),
        "bottom" => Ok(BoardSide::Bottom),
        other => Err(PyValueError::new_err(format!(
            "invalid BoardSide: '{other}'. Expected 'top' or 'bottom'"
        ))),
    }
}

pub(crate) fn parse_package_type(s: &str) -> PyResult<PackageType> {
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

const COMPONENT_KEYS: &[&str] = &[
    "ref",
    "x",
    "y",
    "rot",
    "side",
    "width",
    "height",
    "net_class",
    // "voltage_domain": sent by drc_runner.py's _placement_to_board_dict
    // but not read here -- `Component` (board.rs) has no voltage_domain
    // field. This is a KNOWN, already-documented schema gap (see
    // rules/erc/power_domain.rs and drc_result.py's PowerDomainCheck
    // docstring: "the native Rust board schema has no voltage_domain
    // field"), not something this key-set guard is meant to flag.
    // Listed here so a genuinely deliberate, tracked gap doesn't trip the
    // unknown-key guard meant to catch accidental/typo mismatches.
    "voltage_domain",
    "power_dissipation_w",
    "package_type",
    "is_magnetic",
    "is_electrolytic",
    "is_mechanical",
    "vent_direction",
    "footprint_polygon",
];

fn extract_component(dict: &Bound<'_, PyDict>) -> PyResult<Component> {
    reject_unknown_keys(dict, COMPONENT_KEYS, "component")?;
    let refdes = extract_str(dict, "ref")?;
    let x = extract_f64(dict, "x", 0.0)?;
    let y = extract_f64(dict, "y", 0.0)?;
    let rotation = extract_f64(dict, "rot", 0.0)?;
    let side_str = extract_str(dict, "side")?;
    let side = parse_board_side(&side_str)?;
    let width = extract_f64(dict, "width", 0.0)?;
    let height = extract_f64(dict, "height", 0.0)?;
    let net_class = extract_str(dict, "net_class")?;
    let power_dissipation_w = extract_opt_f64(dict, "power_dissipation_w")?;
    let package_type_str = extract_str(dict, "package_type")?;
    let package_type = parse_package_type(&package_type_str)?;
    let is_magnetic = extract_opt_bool(dict, "is_magnetic")?.unwrap_or(false);
    let is_electrolytic = extract_opt_bool(dict, "is_electrolytic")?.unwrap_or(false);
    let vent_direction = extract_opt_f64(dict, "vent_direction")?;
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

const NET_CLASS_RULES_KEYS: &[&str] = &[
    "name",
    "trace_width_mm",
    "clearance_mm",
    "dru_priority",
    "via_diameter",
    "via_drill",
    "via_template",
    "creepage_mm",
    "voltage_v",
    "target_impedance",
    "max_current_rating",
    "required_layer",
    "layer",
    "safety_category",
    "routing_strategy",
];

fn extract_net_class_rules(dict: &Bound<'_, PyDict>) -> PyResult<NetClassRules> {
    reject_unknown_keys(dict, NET_CLASS_RULES_KEYS, "net_class_rules entry")?;
    Ok(NetClassRules {
        name: extract_str(dict, "name").unwrap_or_default(),
        trace_width_mm: extract_f64(dict, "trace_width_mm", 0.2)?,
        clearance_mm: extract_f64(dict, "clearance_mm", 0.2)?,
        dru_priority: extract_f64(dict, "dru_priority", 0.0)?.round() as i32,
        via_diameter: extract_f64(dict, "via_diameter", 0.6)?,
        via_drill: extract_f64(dict, "via_drill", 0.3)?,
        via_template: extract_opt_str(dict, "via_template")?,
        creepage_mm: extract_f64(dict, "creepage_mm", 0.0)?,
        voltage_v: extract_f64(dict, "voltage_v", 0.0)?,
        target_impedance: extract_opt_f64(dict, "target_impedance")?,
        max_current_rating: extract_opt_f64(dict, "max_current_rating")?,
        required_layer: extract_opt_str(dict, "required_layer")?,
        layer: extract_opt_str(dict, "layer")?,
        safety_category: extract_opt_str(dict, "safety_category")?,
        routing_strategy: extract_opt_str(dict, "routing_strategy")?,
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

const TRACE_SEGMENT_KEYS: &[&str] = &["net", "layer", "width", "segments"];

fn extract_trace_segment(dict: &Bound<'_, PyDict>) -> PyResult<TraceSegment> {
    reject_unknown_keys(dict, TRACE_SEGMENT_KEYS, "trace entry")?;
    let net = extract_str(dict, "net")?;
    let layer = extract_str(dict, "layer")?;
    let width = extract_f64(dict, "width", 0.2)?;

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

const VIA_KEYS: &[&str] = &["net", "x", "y", "drill", "pad", "from_layer", "to_layer"];

fn extract_via(dict: &Bound<'_, PyDict>) -> PyResult<Via> {
    reject_unknown_keys(dict, VIA_KEYS, "via entry")?;
    let net = extract_str(dict, "net")?;
    let x = extract_f64(dict, "x", 0.0)?;
    let y = extract_f64(dict, "y", 0.0)?;
    let drill = extract_f64(dict, "drill", 0.3)?;
    let pad = extract_f64(dict, "pad", 0.6)?;
    let from_layer = extract_opt_str(dict, "from_layer")?.unwrap_or_else(|| "F.Cu".into());
    let to_layer = extract_opt_str(dict, "to_layer")?.unwrap_or_else(|| "B.Cu".into());

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

const COPPER_ZONE_KEYS: &[&str] = &["net", "layer", "polygon"];

fn extract_copper_zone(dict: &Bound<'_, PyDict>) -> PyResult<CopperZone> {
    reject_unknown_keys(dict, COPPER_ZONE_KEYS, "zone entry")?;
    let net = extract_str(dict, "net")?;
    let layer = extract_str(dict, "layer")?;
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
) -> PyResult<BTreeMap<NetClassName, NetClassRules>> {
    let mut result = BTreeMap::new();
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
    let trace_list = extract_dict_list(board_dict, "traces")?;
    let mut result = Vec::with_capacity(trace_list.len());
    for trace_dict in trace_list {
        result.push(extract_trace_segment(&trace_dict)?);
    }
    Ok(result)
}

fn parse_zones_from_dict(board_dict: &Bound<'_, PyDict>) -> PyResult<Vec<CopperZone>> {
    let zone_list = extract_dict_list(board_dict, "zones")?;
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
const BOARD_DICT_KEYS: &[&str] = &[
    "board",
    "components",
    "nets",
    "net_classes",
    "net_class_rules",
    "traces",
    "vias",
    "zones",
];

const BOARD_INFO_KEYS: &[&str] = &["width_mm", "height_mm", "margin_mm"];

pub fn build_board_state(board_dict: &Bound<'_, PyDict>) -> PyResult<BoardState> {
    reject_unknown_keys(board_dict, BOARD_DICT_KEYS, "board_dict")?;

    // --- Board dimensions ---
    let board_item = board_dict
        .get_item("board")?
        .ok_or_else(|| PyValueError::new_err("missing required key: board"))?;
    let board_info: Bound<'_, PyDict> = board_item
        .cast_into::<PyDict>()
        .map_err(|e| PyValueError::new_err(format!("key 'board' is not a dict: {e}")))?;
    reject_unknown_keys(&board_info, BOARD_INFO_KEYS, "board_dict['board']")?;

    let width_mm = extract_f64(&board_info, "width_mm", 100.0)?;
    let height_mm = extract_f64(&board_info, "height_mm", 150.0)?;
    let margin_mm = extract_f64(&board_info, "margin_mm", 3.0)?;

    // --- Components ---
    let (electrical_components, mechanical_components) = {
        let comp_list = extract_dict_list(board_dict, "components")?;
        let mut elec = Vec::with_capacity(comp_list.len());
        let mut mech = Vec::new();
        for comp_dict in comp_list {
            let is_mechanical = extract_opt_bool(&comp_dict, "is_mechanical")?.unwrap_or(false);
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
    //
    // SAFETY (mains-voltage board, IEC 60335-1 isolation barrier): an
    // unresolvable net class used to fall back to the thinnest rule set on
    // the board (0.2mm trace / 0.2mm clearance) rather than an error or the
    // strictest rule. That is fail-OPEN: a mains net whose class lookup
    // silently no-ops (a stale/mistyped `net_classes` config key, see
    // `scripts/check_netclass_map_board_correspondence.py`) would be
    // DRC-checked against 0.2mm clearance instead of e.g. an 8.0mm
    // reinforced-creepage requirement, and CI would report clean.
    //
    // Both failure modes below are now hard errors -- BUT ONLY when the
    // caller supplied `net_classes` / `net_class_rules` at all: an EMPTY
    // map means this caller's schema never carries that dimension (the
    // CP-SAT/router `Placement` schema has no per-net `net_class_rules`
    // concept at all -- see `drc_marshal::DrcBoardSnapshot::from_state`,
    // and `router_v6/_pipeline_verify.py::_parsed_pcb_to_drc_input` never
    // populates `Placement.net_classes` even in production), so refusing
    // to run there would make DRC entirely inoperable for those callers,
    // not catch a real misconfiguration. A NON-empty map that is missing
    // THIS ONE net is the actual bug this closes: the caller clearly
    // intended per-net classification and has a gap. See
    // docs/evidence/2026-08-11-typed-net-refs-spike.md and the PR that
    // added this comment for the incident this closes.
    let net_classes_wired = !net_classes_raw.is_empty();
    let net_class_rules_wired = !net_class_rules.is_empty();
    let nets: Vec<Net> = nets_dict_raw
        .into_iter()
        .map(|(name, comps)| -> PyResult<Net> {
            let net_name = NetName(name.clone());
            let resolved = net_classes_raw.get(&name).map(|c| NetClassName(c.clone()));
            let class_name = match resolved {
                Some(c) => c,
                None if net_classes_wired => {
                    return Err(PyValueError::new_err(format!(
                        "net {name:?} has no entry in net_classes -- refusing \
                         to run DRC with an unclassified net silently \
                         defaulted to the thinnest rule set on the board. \
                         Add an explicit net_classes entry for this net."
                    )));
                }
                None => NetClassName("Unknown".to_string()),
            };
            let found_rules = net_class_rules.get(&class_name).cloned();
            let rules = match found_rules {
                Some(r) => r,
                None if net_class_rules_wired => {
                    let class_str = &class_name.0;
                    return Err(PyValueError::new_err(format!(
                        "net {name:?} is classed {class_str:?} but net_class_rules \
                         has no entry for class {class_str:?} -- refusing to run \
                         DRC with an unresolvable net class silently defaulted \
                         to the thinnest rule set on the board. Define \
                         net_class_rules[{class_str:?}] or correct the net's \
                         class."
                    )));
                }
                None => NetClassRules {
                    trace_width_mm: 0.2,
                    clearance_mm: 0.2,
                    ..NetClassRules::default()
                },
            };
            Ok(Net {
                name: net_name,
                components: comps.into_iter().map(ComponentRef).collect(),
                class: class_name,
                rules,
            })
        })
        .collect::<PyResult<Vec<Net>>>()?;

    // --- Traces (optional) ---
    let traces = parse_traces_from_dict(board_dict)?;

    // --- Vias (optional) ---
    let vias = {
        let via_list = extract_dict_list(board_dict, "vias")?;
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

// ---------------------------------------------------------------------------
// Rust unit tests
// ---------------------------------------------------------------------------

#[cfg(test)]
// Test-only assertions; unwrap/expect on a known-good fixture is the idiom
// used throughout this crate's test modules (see e.g. board.rs, manufacturing.rs).
#[allow(clippy::unwrap_used, clippy::expect_used)]
mod tests {
    use super::*;

    /// Build a minimal K1-schema board dict with two nets: "OTHER_NET"
    /// (always classed "Signal", with matching rules -- keeps
    /// `net_classes`/`net_class_rules` "wired" i.e. non-empty, so the tests
    /// below exercise the real "caller intended classification but has a
    /// gap for THIS net" shape) and "MAINS_L", whose classification is
    /// controlled by `net_classes_entry` / `net_class_rules_entry`.
    ///
    /// `wired` controls whether "OTHER_NET" is included at all: with
    /// `wired=false` the whole board has zero `net_classes`/
    /// `net_class_rules` entries, matching a caller (e.g. the CP-SAT/router
    /// `Placement` schema) that never carries this dimension at all.
    fn board_dict_with_two_nets<'py>(
        py: Python<'py>,
        wired: bool,
        net_classes_entry: Option<(&str, &str)>,
        net_class_rules_entry: Option<(&str, f64, f64)>,
    ) -> Bound<'py, PyDict> {
        let board_dict = PyDict::new(py);
        let board_info = PyDict::new(py);
        board_info.set_item("width_mm", 100.0).unwrap();
        board_info.set_item("height_mm", 100.0).unwrap();
        board_info.set_item("margin_mm", 3.0).unwrap();
        board_dict.set_item("board", board_info).unwrap();

        let nets = PyDict::new(py);
        nets.set_item("MAINS_L", PyList::new(py, ["J1"]).unwrap()).unwrap();
        if wired {
            nets.set_item("OTHER_NET", PyList::new(py, ["J2"]).unwrap()).unwrap();
        }
        board_dict.set_item("nets", nets).unwrap();

        let net_classes = PyDict::new(py);
        if wired {
            net_classes.set_item("OTHER_NET", "Signal").unwrap();
        }
        if let Some((net, class)) = net_classes_entry {
            net_classes.set_item(net, class).unwrap();
        }
        board_dict.set_item("net_classes", net_classes).unwrap();

        let net_class_rules = PyDict::new(py);
        if wired {
            let signal_rules = PyDict::new(py);
            signal_rules.set_item("trace_width_mm", 0.25).unwrap();
            signal_rules.set_item("clearance_mm", 0.2).unwrap();
            net_class_rules.set_item("Signal", signal_rules).unwrap();
        }
        if let Some((class, trace_width_mm, clearance_mm)) = net_class_rules_entry {
            let rules = PyDict::new(py);
            rules.set_item("trace_width_mm", trace_width_mm).unwrap();
            rules.set_item("clearance_mm", clearance_mm).unwrap();
            net_class_rules.set_item(class, rules).unwrap();
        }
        board_dict.set_item("net_class_rules", net_class_rules).unwrap();

        board_dict
    }

    fn mains_net(state: &BoardState) -> &Net {
        state.nets.iter().find(|n| n.name.0 == "MAINS_L").unwrap()
    }

    #[test]
    fn unclassified_net_is_hard_error_when_net_classes_is_wired() {
        // "MAINS_L" has no entry in net_classes, but "OTHER_NET" does --
        // net_classes is clearly wired up for this board, so a gap for one
        // specific net is the real bug, not "this caller doesn't classify
        // nets at all".
        pyo3::Python::initialize();
        pyo3::Python::attach(|py| {
            let dict = board_dict_with_two_nets(py, true, None, None);
            let err = build_board_state(&dict)
                .expect_err("a net absent from a wired-up net_classes must be a hard error");
            let msg = err.to_string();
            assert!(msg.contains("MAINS_L"), "error should name the net: {msg}");
            assert!(
                msg.contains("net_classes"),
                "error should name the missing mapping: {msg}"
            );
        });
    }

    #[test]
    fn unmatched_net_class_is_hard_error_when_net_class_rules_is_wired() {
        // "MAINS_L" resolves to class "ACMains", but net_class_rules only
        // defines "Signal" -- the shape a stale/mistyped net_classes config
        // key produces in practice (see
        // scripts/check_netclass_map_board_correspondence.py).
        pyo3::Python::initialize();
        pyo3::Python::attach(|py| {
            let dict = board_dict_with_two_nets(py, true, Some(("MAINS_L", "ACMains")), None);
            let err = build_board_state(&dict)
                .expect_err("a class absent from a wired-up net_class_rules must be a hard error");
            let msg = err.to_string();
            assert!(msg.contains("MAINS_L"), "error should name the net: {msg}");
            assert!(msg.contains("ACMains"), "error should name the unresolved class: {msg}");
            assert!(
                msg.contains("net_class_rules"),
                "error should name the missing mapping: {msg}"
            );
        });
    }

    /// Regression: an unresolvable net class used to fall back to
    /// `trace_width_mm: 0.2, clearance_mm: 0.2` (the thinnest rule set on
    /// the board) instead of erroring. Prove that shape is categorically
    /// gone whenever the caller wired up classification at all: EVERY
    /// unresolvable net on a wired-up board produces `Err`, so there is no
    /// `Ok` board left for a silently-thinned 0.2/0.2 `NetClassRules` to
    /// hide in.
    #[test]
    fn regression_unresolvable_net_never_yields_thin_default_rules_when_wired() {
        pyo3::Python::initialize();
        pyo3::Python::attach(|py| {
            for dict in [
                board_dict_with_two_nets(py, true, None, None),
                board_dict_with_two_nets(py, true, Some(("MAINS_L", "ACMains")), None),
            ] {
                match build_board_state(&dict) {
                    Err(_) => {} // correct: fails loudly instead of silently thinning.
                    Ok(state) => {
                        let net = mains_net(&state);
                        panic!(
                            "pre-fix regression: unresolved net class silently produced \
                             trace_width_mm={}, clearance_mm={} instead of erroring \
                             (net={:?}, class={:?})",
                            net.rules.trace_width_mm, net.rules.clearance_mm, net.name, net.class
                        );
                    }
                }
            }
        });
    }

    /// Sanity/no-false-positive: a net whose class DOES resolve still
    /// builds successfully, with the real (non-thinned) rules.
    #[test]
    fn resolvable_net_class_still_succeeds() {
        pyo3::Python::initialize();
        pyo3::Python::attach(|py| {
            let dict = board_dict_with_two_nets(
                py,
                true,
                Some(("MAINS_L", "ACMains")),
                Some(("ACMains", 1.5, 8.0)),
            );
            let state = build_board_state(&dict).expect("resolvable net class must not error");
            let net = mains_net(&state);
            assert_eq!(net.rules.clearance_mm, 8.0);
            assert_eq!(net.rules.trace_width_mm, 1.5);
        });
    }

    /// A caller that supplies NO `net_classes`/`net_class_rules` at all
    /// (both maps entirely empty) is a schema that never carries per-net
    /// classification -- e.g. `DrcBoardSnapshot::from_state`, the CP-SAT/
    /// router `Placement` path, which has no per-net `net_class_rules`
    /// concept at all, and whose real caller
    /// (`router_v6/_pipeline_verify.py::_parsed_pcb_to_drc_input`) never
    /// populates `Placement.net_classes` even in production. Hard-erroring
    /// there would make DRC entirely inoperable for that caller instead of
    /// catching a real misconfiguration, so the legacy "Unknown" class /
    /// thin default is preserved ONLY in this all-absent case.
    #[test]
    fn completely_unwired_board_keeps_legacy_default_not_a_hard_error() {
        pyo3::Python::initialize();
        pyo3::Python::attach(|py| {
            let dict = board_dict_with_two_nets(py, false, None, None);
            let state =
                build_board_state(&dict).expect("a completely unwired board must not error");
            let net = mains_net(&state);
            assert_eq!(net.class.0, "Unknown");
            assert_eq!(net.rules.trace_width_mm, 0.2);
            assert_eq!(net.rules.clearance_mm, 0.2);
        });
    }
}
