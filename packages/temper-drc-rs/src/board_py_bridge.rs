// PyO3 bridge helpers: extract typed values from Python dicts.
//
// Follows the `HashMapResolver` pattern from
// `packages/temper-constraint-compiler/src/pyo3_bridge.rs`.
//
// All extraction functions produce descriptive PyValueError messages
// on type mismatch or missing required keys.
//
// Origin: U2 of docs/plans/2026-06-30-003-feat-temper-drc-rs-engine-plan.md

use std::collections::HashMap;

use geo::{Line, Point, Polygon};
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::{PyAny, PyDict, PyList};

use crate::board::{
    BoardSide, BoardState, Component, CopperZone, NetClassRules, PackageType, TraceSegment, Via,
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
            let list: &Bound<'_, PyList> = val.downcast().map_err(|e| {
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
            let list: &Bound<'_, PyList> = val.downcast().map_err(|e| {
                PyValueError::new_err(format!("key '{key}' is not a list: {e}"))
            })?;
            let mut result = Vec::with_capacity(list.len());
            for item in list.iter() {
                let d: &Bound<'_, PyDict> = item.downcast().map_err(|e| {
                    PyValueError::new_err(format!(
                        "item in '{key}' list is not a dict: {e}"
                    ))
                })?;
                result.push(d.clone());
            }
            Ok(result)
        }
        _ => Ok(Vec::new()),
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
    let inner: &Bound<'_, PyDict> = item
        .downcast::<PyDict>()
        .map_err(|e| PyValueError::new_err(format!("key '{key}' is not a dict: {e}")))?;
    let x = extract_f64(inner, "x", 0.0)?;
    let y = extract_f64(inner, "y", 0.0)?;
    Ok(Point::new(x, y))
}

/// Extract an optional geo::Point from a dict.
pub fn extract_opt_point(dict: &Bound<'_, PyDict>, key: &str) -> PyResult<Option<Point<f64>>> {
    match dict.get_item(key)? {
        Some(val) if !val.is_none() && val.is_instance_of::<PyDict>() => {
            let inner: &Bound<'_, PyDict> = val.downcast().unwrap();
            let x = extract_f64(inner, "x", 0.0)?;
            let y = extract_f64(inner, "y", 0.0)?;
            Ok(Some(Point::new(x, y)))
        }
        _ => Ok(None),
    }
}

/// Extract a geo::Polygon from a list of coordinate pairs.
///
/// The Python value should be a list of [x, y] pairs forming the
/// polygon exterior ring (assumed closed — first point need not
/// equal last point; the polygon is auto-closed).
pub fn extract_polygon(dict: &Bound<'_, PyDict>, key: &str) -> PyResult<Polygon<f64>> {
    let val = dict
        .get_item(key)?
        .ok_or_else(|| PyValueError::new_err(format!("missing required key: {key}")))?;

    let list: &Bound<'_, PyList> = val.downcast().map_err(|e| {
        PyValueError::new_err(format!("key '{key}' is not a list: {e}"))
    })?;

    let coords: Vec<(f64, f64)> = list
        .iter()
        .map(|item| -> PyResult<(f64, f64)> {
            let pair: &Bound<'_, PyList> = item.downcast().map_err(|e| {
                PyValueError::new_err(format!(
                    "coordinate in '{key}' polygon is not a list of 2 numbers: {e}"
                ))
            })?;
            if pair.len() < 2 {
                return Err(PyValueError::new_err(format!(
                    "coordinate in '{key}' polygon has fewer than 2 elements"
                )));
            }
            let x: f64 = pair.get_item(0).unwrap().extract().map_err(|e| {
                PyValueError::new_err(format!("x coordinate in '{key}' polygon: {e}"))
            })?;
            let y: f64 = pair.get_item(1).unwrap().extract().map_err(|e| {
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

/// Extract an optional polygon.
pub fn extract_opt_polygon(
    dict: &Bound<'_, PyDict>,
    key: &str,
) -> PyResult<Option<Polygon<f64>>> {
    match dict.get_item(key)? {
        Some(val) if !val.is_none() => {
            // Create a temporary dict so we can reuse extract_polygon
            let inner = PyDict::new(dict.py());
            inner.set_item(key, val.clone()).unwrap();
            let poly = extract_polygon(&inner, key)?;
            Ok(Some(poly))
        }
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
    let is_mechanical = extract_opt_bool(dict, "is_mechanical")?.unwrap_or(false);
    let vent_direction = extract_opt_f64(dict, "vent_direction")?;
    let footprint_polygon = extract_opt_polygon(dict, "footprint_polygon")?;

    Ok(Component {
        refdes,
        center: Point::new(x, y),
        rotation,
        side,
        width,
        height,
        net_class,
        power_dissipation_w,
        package_type,
        is_magnetic,
        is_electrolytic,
        is_mechanical,
        vent_direction,
        footprint_polygon,
    })
}

// ---------------------------------------------------------------------------
// NetClassRules extraction
// ---------------------------------------------------------------------------

fn extract_net_class_rules(dict: &Bound<'_, PyDict>) -> PyResult<NetClassRules> {
    Ok(NetClassRules {
        trace_width_mm: extract_f64(dict, "trace_width_mm", 0.2)?,
        clearance_mm: extract_f64(dict, "clearance_mm", 0.2)?,
        creepage_mm: extract_opt_f64(dict, "creepage_mm")?,
        voltage_v: extract_opt_f64(dict, "voltage_v")?,
        max_current_rating: extract_opt_f64(dict, "max_current_rating")?,
        safety_category: extract_opt_str(dict, "safety_category")?,
        required_layer: extract_opt_str(dict, "required_layer")?,
        routing_strategy: extract_opt_str(dict, "routing_strategy")?,
    })
}

// ---------------------------------------------------------------------------
// Trace extraction
// ---------------------------------------------------------------------------

/// Extract a list of f64 numbers from a list value.
fn extract_f64_list(val: &Bound<'_, PyAny>) -> PyResult<Vec<f64>> {
    let list: &Bound<'_, PyList> = val.downcast().map_err(|e| {
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
    let net = extract_str(dict, "net")?;
    let layer = extract_str(dict, "layer")?;
    let width = extract_f64(dict, "width", 0.2)?;

    // Segments from Python: [[x1, y1, x2, y2], [x1, y1, x2, y2], ...]
    let mut segments = Vec::new();
    if let Some(segments_val) = dict.get_item("segments")? {
        if !segments_val.is_none() && segments_val.is_instance_of::<PyList>() {
            let seg_list: &Bound<'_, PyList> = segments_val.downcast().unwrap();
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
    }

    Ok(TraceSegment {
        net,
        layer,
        width,
        segments,
    })
}

// ---------------------------------------------------------------------------
// Via extraction
// ---------------------------------------------------------------------------

fn extract_via(dict: &Bound<'_, PyDict>) -> PyResult<Via> {
    let net = extract_str(dict, "net")?;
    let x = extract_f64(dict, "x", 0.0)?;
    let y = extract_f64(dict, "y", 0.0)?;
    let drill = extract_f64(dict, "drill", 0.3)?;
    let pad = extract_f64(dict, "pad", 0.6)?;
    let from_layer = extract_opt_str(dict, "from_layer")?.unwrap_or_else(|| "F.Cu".into());
    let to_layer = extract_opt_str(dict, "to_layer")?.unwrap_or_else(|| "B.Cu".into());

    Ok(Via {
        net,
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
    let net = extract_str(dict, "net")?;
    let layer = extract_str(dict, "layer")?;
    let polygon = extract_polygon(dict, "polygon")?;

    Ok(CopperZone { net, layer, polygon })
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
    let board_info: &Bound<'_, PyDict> = board_item
        .downcast()
        .map_err(|e| PyValueError::new_err(format!("key 'board' is not a dict: {e}")))?;

    let width_mm = extract_f64(board_info, "width_mm", 100.0)?;
    let height_mm = extract_f64(board_info, "height_mm", 150.0)?;
    let margin_mm = extract_f64(board_info, "margin_mm", 3.0)?;

    // --- Components ---
    let components = {
        let comp_list = extract_dict_list(board_dict, "components")?;
        let mut result = Vec::with_capacity(comp_list.len());
        for comp_dict in comp_list {
            result.push(extract_component(&comp_dict)?);
        }
        result
    };

    // --- Nets ---
    let nets: HashMap<String, Vec<String>> = {
        let mut result = HashMap::new();
        if let Some(nets_val) = board_dict.get_item("nets")? {
            if !nets_val.is_none() && nets_val.is_instance_of::<PyDict>() {
                let nets_dict: &Bound<'_, PyDict> = nets_val.downcast().unwrap();
                for (key, val) in nets_dict.iter() {
                    let net_name: String = key.extract().map_err(|e| {
                        PyValueError::new_err(format!("nets key is not a string: {e}"))
                    })?;
                    let list: &Bound<'_, PyList> = val.downcast().map_err(|e| {
                        PyValueError::new_err(format!(
                            "nets['{net_name}'] is not a list: {e}"
                        ))
                    })?;
                    let comps: Vec<String> = list
                        .iter()
                        .map(|item| item.extract::<String>().map_err(|e| {
                            PyValueError::new_err(format!(
                                "component ref in nets['{net_name}'] is not a string: {e}"
                            ))
                        }))
                        .collect::<Result<Vec<_>, _>>()?;
                    result.insert(net_name, comps);
                }
            }
        }
        result
    };

    // --- Net classes ---
    let net_classes: HashMap<String, String> = {
        let mut result = HashMap::new();
        if let Some(nc_val) = board_dict.get_item("net_classes")? {
            if !nc_val.is_none() && nc_val.is_instance_of::<PyDict>() {
                let nc_dict: &Bound<'_, PyDict> = nc_val.downcast().unwrap();
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
        }
        result
    };

    // --- Net class rules ---
    let net_class_rules: HashMap<String, NetClassRules> = {
        let mut result = HashMap::new();
        if let Some(ncr_val) = board_dict.get_item("net_class_rules")? {
            if !ncr_val.is_none() && ncr_val.is_instance_of::<PyDict>() {
                let ncr_dict: &Bound<'_, PyDict> = ncr_val.downcast().unwrap();
                for (key, val) in ncr_dict.iter() {
                    let class_name: String = key.extract().map_err(|e| {
                        PyValueError::new_err(format!(
                            "net_class_rules key is not a string: {e}"
                        ))
                    })?;
                    let rules_dict: &Bound<'_, PyDict> = val.downcast().map_err(|e| {
                        PyValueError::new_err(format!(
                            "net_class_rules['{class_name}'] is not a dict: {e}"
                        ))
                    })?;
                    result.insert(class_name, extract_net_class_rules(rules_dict)?);
                }
            }
        }
        result
    };

    // --- Traces (optional) ---
    let traces = {
        let trace_list = extract_dict_list(board_dict, "traces")?;
        let mut result = Vec::with_capacity(trace_list.len());
        for trace_dict in trace_list {
            result.push(extract_trace_segment(&trace_dict)?);
        }
        result
    };

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
    let zones = {
        let zone_list = extract_dict_list(board_dict, "zones")?;
        let mut result = Vec::with_capacity(zone_list.len());
        for zone_dict in zone_list {
            result.push(extract_copper_zone(&zone_dict)?);
        }
        result
    };

    Ok(BoardState {
        width_mm,
        height_mm,
        margin_mm,
        components,
        nets,
        net_classes,
        net_class_rules,
        traces,
        vias,
        zones,
    })
}
