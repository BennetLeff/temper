use std::collections::HashMap;

use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};
use pyo3::Py;

use crate::desugar_tier0::compile_tier0_to_tier1;
use crate::desugar_tier1::compile_tier1_to_tier2;
use crate::ir_tier0::{ConstraintTier, PclConstraint, PclConstraintModel, Point, Rect};
use crate::ir_tier1::{
    Channel, ChannelTopology, ComponentResolver, ZoneResolver,
};
use crate::provenance::{detect_conflicts, ProvenanceMap};
use crate::type_lattice::{NetClassMetadata, SafetyCategory, TypeLattice};

macro_rules! extract {
    ($dict:expr, str: $key:literal) => { extract_str($dict, $key)? };
    ($dict:expr, opt_str: $key:literal) => { extract_opt_str($dict, $key)? };
    ($dict:expr, f64: $key:literal, $default:expr) => { extract_f64($dict, $key, $default)? };
    ($dict:expr, str_list: $key:literal) => { extract_str_list($dict, $key)? };
    ($dict:expr, opt_rect) => { extract_opt_rect($dict)? };
    ($dict:expr, opt_point) => { extract_opt_point($dict)? };
}

#[derive(Clone)]
pub struct HashMapResolver {
    pub component_map: HashMap<String, usize>,
    pub zone_map: HashMap<String, Rect>,
}

impl ComponentResolver for HashMapResolver {
    fn resolve(&self, component_ref: &str) -> Option<usize> {
        self.component_map.get(component_ref).copied()
    }
}

impl ZoneResolver for HashMapResolver {
    fn resolve(&self, zone_name: &str) -> Option<Rect> {
        self.zone_map.get(zone_name).copied()
    }
}

fn extract_str(dict: &Bound<'_, PyDict>, key: &str) -> PyResult<String> {
    dict.get_item(key)?
        .ok_or_else(|| {
            PyErr::new::<pyo3::exceptions::PyValueError, _>(format!("missing key: {key}"))
        })?
        .extract()
}

fn extract_opt_str(dict: &Bound<'_, PyDict>, key: &str) -> PyResult<Option<String>> {
    match dict.get_item(key)? {
        Some(val) if !val.is_none() => Ok(Some(val.extract()?)),
        _ => Ok(None),
    }
}

fn extract_f64(dict: &Bound<'_, PyDict>, key: &str, default: f64) -> PyResult<f64> {
    match dict.get_item(key)? {
        Some(val) => {
            if val.is_none() {
                Ok(default)
            } else {
                val.extract()
            }
        }
        None => Ok(default),
    }
}

fn extract_str_list(dict: &Bound<'_, PyDict>, key: &str) -> PyResult<Vec<String>> {
    match dict.get_item(key)? {
        Some(val) if !val.is_none() => {
            let list: Bound<'_, PyList> = val.cast_into::<PyList>()?;
            let mut result = Vec::new();
            for item in list {
                result.push(item.extract::<String>()?);
            }
            Ok(result)
        }
        _ => Ok(Vec::new()),
    }
}

fn extract_opt_rect(dict: &Bound<'_, PyDict>) -> PyResult<Option<Rect>> {
    match dict.get_item("region")? {
        Some(val) if !val.is_none() && val.is_instance_of::<PyDict>() => {
            let rd: Bound<'_, PyDict> = val.cast_into::<PyDict>()?;
            Ok(Some(Rect {
                x_min: extract_f64(&rd, "x_min", 0.0)?,
                y_min: extract_f64(&rd, "y_min", 0.0)?,
                x_max: extract_f64(&rd, "x_max", 0.0)?,
                y_max: extract_f64(&rd, "y_max", 0.0)?,
            }))
        }
        _ => Ok(None),
    }
}

fn extract_opt_point(dict: &Bound<'_, PyDict>) -> PyResult<Option<Point>> {
    match dict.get_item("position")? {
        Some(val) if !val.is_none() && val.is_instance_of::<PyDict>() => {
            let pd: Bound<'_, PyDict> = val.cast_into::<PyDict>()?;
            Ok(Some(Point {
                x: extract_f64(&pd, "x", 0.0)?,
                y: extract_f64(&pd, "y", 0.0)?,
            }))
        }
        _ => Ok(None),
    }
}

fn extract_common_fields(dict: &Bound<'_, PyDict>) -> PyResult<(String, ConstraintTier, String)> {
    let id = extract_str(dict, "id").unwrap_or_else(|_| "unnamed".into());
    let tier_str = extract_str(dict, "tier").unwrap_or_else(|_| "HARD".into());
    let tier = ConstraintTier::parse(&tier_str).ok_or_else(|| {
        PyErr::new::<pyo3::exceptions::PyTypeError, _>(format!("invalid tier: {tier_str}"))
    })?;
    let because = extract_str(dict, "because").unwrap_or_else(|_| "no rationale".into());
    Ok((id, tier, because))
}

fn pcl_constraint_from_py_dict(dict: &Bound<'_, PyDict>) -> PyResult<PclConstraint> {
    let ctype: String = extract_str(dict, "type")?;
    let (id, tier, because) = extract_common_fields(dict)?;

    match ctype.as_str() {
        "adjacent" | "Adjacent" => {
            let a = extract!(dict, str: "a");
            let b = extract!(dict, str: "b");
            let max_distance_mm = extract!(dict, f64: "max_distance_mm", 0.0);
            let metric = extract!(dict, opt_str: "metric");
            let pin_a = extract!(dict, opt_str: "pin_a");
            let pin_b = extract!(dict, opt_str: "pin_b");
            Ok(PclConstraint::Adjacent { id, a, b, max_distance_mm, tier, because, metric, pin_a, pin_b })
        }
        "separated" | "Separated" => {
            let a = extract!(dict, str: "a");
            let b = extract!(dict, str: "b");
            let min_distance_mm = extract!(dict, f64: "min_distance_mm", 0.0);
            let metric = extract!(dict, opt_str: "metric");
            Ok(PclConstraint::Separated { id, a, b, min_distance_mm, tier, because, metric })
        }
        "enclosing" | "Enclosing" => {
            let outer = extract!(dict, str: "outer");
            let inner = extract!(dict, str_list: "inner");
            let margin_mm = extract!(dict, f64: "margin_mm", 0.0);
            Ok(PclConstraint::Enclosing { id, outer, inner, margin_mm, tier, because })
        }
        "aligned" | "Aligned" => {
            let components = extract!(dict, str_list: "components");
            let axis_str = extract!(dict, opt_str: "axis");
            let axis = axis_str.and_then(|s| crate::ir_tier0::Axis::parse(&s));
            let tolerance_mm = extract!(dict, f64: "tolerance_mm", 0.0);
            Ok(PclConstraint::Aligned { id, components, axis, tolerance_mm, tier, because })
        }
        "on_side" | "OnSide" => {
            let components = extract!(dict, str_list: "components");
            let side_str = extract!(dict, opt_str: "side");
            let side = side_str.and_then(|s| crate::ir_tier0::BoardEdge::parse(&s));
            let edge = extract!(dict, opt_str: "edge");
            let max_distance_mm = extract!(dict, f64: "max_distance_mm", 0.0);
            Ok(PclConstraint::OnSide { id, components, side, edge, max_distance_mm, tier, because })
        }
        "anchored" | "Anchored" => {
            let component = extract!(dict, str: "component");
            let region = extract!(dict, opt_rect);
            let position = extract!(dict, opt_point);
            Ok(PclConstraint::Anchored { id, component, region, position, tier, because })
        }
        "loop_area" | "LoopArea" => {
            let loop_name = extract!(dict, str: "loop_name");
            let max_area_mm2 = extract!(dict, f64: "max_area_mm2", 0.0);
            let components = extract!(dict, str_list: "components");
            Ok(PclConstraint::LoopArea { id, loop_name, max_area_mm2, tier, because, components })
        }
        _ => Err(PyErr::new::<pyo3::exceptions::PyTypeError, _>(format!(
            "unknown constraint type: {ctype}"
        ))),
    }
}

pub fn build_pcl_constraints_from_py(
    dicts: &Bound<'_, PyList>,
) -> PyResult<Vec<PclConstraint>> {
    let mut constraints = Vec::new();
    for item in dicts {
        let d: Bound<'_, PyDict> = item.cast_into::<PyDict>()?;
        constraints.push(pcl_constraint_from_py_dict(&d)?);
    }
    Ok(constraints)
}

fn net_class_metadata_from_py_dict(
    dict: &Bound<'_, PyDict>,
) -> PyResult<NetClassMetadata> {
    let class_name: String = extract_str(dict, "name")?;
    let safety_str: Option<String> = extract_opt_str(dict, "safety_category")?;
    let safety_category = safety_str.and_then(|s| SafetyCategory::parse(&s));
    let clearance: f64 = extract_f64(dict, "clearance", 0.0)?;
    let creepage_mm: f64 = extract_f64(dict, "creepage_mm", 0.0)?;
    let required_layer: Option<String> = extract_opt_str(dict, "required_layer")?;
    let dru_priority: Option<u32> = match dict.get_item("dru_priority")? {
        Some(val) if !val.is_none() => {
            let v: i64 = val.extract()?;
            Some(v as u32)
        }
        _ => None,
    };
    Ok(NetClassMetadata {
        class_name,
        safety_category,
        clearance,
        creepage_mm,
        required_layer,
        dru_priority,
    })
}

pub fn build_net_class_metadata_from_py(
    dicts: &Bound<'_, PyList>,
) -> PyResult<Vec<NetClassMetadata>> {
    let mut metadata = Vec::new();
    for item in dicts {
        let d: Bound<'_, PyDict> = item.cast_into::<PyDict>()?;
        metadata.push(net_class_metadata_from_py_dict(&d)?);
    }
    Ok(metadata)
}

pub fn build_component_map_from_py_dict(
    py_dict: &Bound<'_, PyDict>,
) -> PyResult<HashMap<String, usize>> {
    let mut map = HashMap::new();
    for (key, value) in py_dict {
        let k: String = key.extract()?;
        let v: usize = value.extract()?;
        map.insert(k, v);
    }
    Ok(map)
}

pub fn build_zone_map_from_py_dict(
    py_dict: &Bound<'_, PyDict>,
) -> PyResult<HashMap<String, Rect>> {
    let mut map = HashMap::new();
    for (key, value) in py_dict {
        let k: String = key.extract()?;
        let d: Bound<'_, PyDict> = value.cast_into::<PyDict>()?;
        let rect = Rect {
            x_min: extract_f64(&d, "x_min", 0.0)?,
            y_min: extract_f64(&d, "y_min", 0.0)?,
            x_max: extract_f64(&d, "x_max", 0.0)?,
            y_max: extract_f64(&d, "y_max", 0.0)?,
        };
        map.insert(k, rect);
    }
    Ok(map)
}

pub fn build_channel_topology_from_py(
    skeletons: &Bound<'_, PyList>,
    channel_widths: &Bound<'_, PyDict>,
) -> PyResult<ChannelTopology> {
    let mut channels_map: HashMap<String, Channel> = HashMap::new();

    for item in skeletons {
        let d: Bound<'_, PyDict> = item.cast_into::<PyDict>()?;
        let ch_id: String = extract_str(&d, "channel_id")
            .or_else(|_| extract_str(&d, "channel"))?;
        let net_a: usize = extract_str(&d, "net_a")
            .or_else(|_| extract_str(&d, "net1"))?
            .parse()
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(format!("{e}")))?;
        let net_b: usize = extract_str(&d, "net_b")
            .or_else(|_| extract_str(&d, "net2"))?
            .parse()
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(format!("{e}")))?;
        let width: f64 = channel_widths
            .get_item(&ch_id)?
            .map(|v| v.extract::<f64>().unwrap_or(2.0))
            .unwrap_or(2.0);
        let layer: String = extract_str(&d, "layer").unwrap_or_else(|_| "F.Cu".into());

        let entry = channels_map
            .entry(ch_id.clone())
            .or_insert_with(|| Channel {
                id: ch_id.clone(),
                width_mm: width,
                nets: Vec::new(),
                layer,
            });
        if !entry.nets.contains(&net_a) {
            entry.nets.push(net_a);
        }
        if !entry.nets.contains(&net_b) {
            entry.nets.push(net_b);
        }
    }

    let channels: Vec<Channel> = channels_map.into_values().collect();
    Ok(ChannelTopology::new(channels))
}

pub fn internal_constraint_to_py_dict(
    py: Python<'_>,
    constraint: &temper_rust_router_core::types::InternalConstraint,
) -> PyResult<Py<PyAny>> {
    let d = PyDict::new(py);
    match constraint {
        temper_rust_router_core::types::InternalConstraint::Capacity {
            channel_id,
            capacity,
            slack_factor,
            terms,
        } => {
            d.set_item("type", "capacity")?;
            d.set_item("channel_id", channel_id)?;
            d.set_item("capacity", capacity)?;
            d.set_item("slack_factor", slack_factor)?;
            let py_terms = PyList::empty(py);
            for (var_name, width) in terms {
                let t = PyDict::new(py);
                t.set_item("var_name", var_name)?;
                t.set_item("width", width)?;
                py_terms.append(t)?;
            }
            d.set_item("terms", py_terms)?;
        }
        temper_rust_router_core::types::InternalConstraint::DiffPair {
            channel_id,
            p_var_name,
            n_var_name,
        } => {
            d.set_item("type", "diff_pair")?;
            d.set_item("channel_id", channel_id)?;
            d.set_item("p_var_name", p_var_name)?;
            d.set_item("n_var_name", n_var_name)?;
        }
        temper_rust_router_core::types::InternalConstraint::LayerRestriction {
            var_name,
            allowed,
        } => {
            d.set_item("type", "layer_restriction")?;
            d.set_item("var_name", var_name)?;
            d.set_item("allowed", allowed)?;
        }
        temper_rust_router_core::types::InternalConstraint::ChannelSeparation {
            group_a,
            group_b,
            min_slots,
            channel_id,
        } => {
            d.set_item("type", "channel_separation")?;
            d.set_item("group_a", group_a.clone())?;
            d.set_item("group_b", group_b.clone())?;
            d.set_item("min_slots", *min_slots as i64)?;
            d.set_item("channel_id", channel_id)?;
        }
    }
    Ok(d.into())
}

pub fn diagnostic_to_py_dict(py: Python<'_>, diag: &crate::provenance::ProvenanceDiagnostic) -> PyResult<Py<PyAny>> {
    let d = PyDict::new(py);
    d.set_item("pcl_constraint_id", &diag.pcl_constraint_id)?;
    d.set_item("tier", format!("{}", diag.tier))?;
    d.set_item("rationale", &diag.rationale)?;
    d.set_item("conflict_with", diag.conflict_with.clone())?;
    d.set_item("clause_indices", diag.clause_indices.clone())?;
    Ok(d.into())
}

#[allow(clippy::too_many_arguments)]
pub fn run_full_pipeline(
    py: Python<'_>,
    pcl_dicts: &Bound<'_, PyList>,
    net_class_dicts: &Bound<'_, PyList>,
    component_map: &Bound<'_, PyDict>,
    zone_map: &Bound<'_, PyDict>,
    skeletons: &Bound<'_, PyList>,
    channel_widths: &Bound<'_, PyDict>,
    _existing_vars: &Bound<'_, PyList>,
    _existing_cons: &Bound<'_, PyList>,
    _net_names: Vec<String>,
) -> PyResult<Py<PyAny>> {
    let mut warnings: Vec<String> = Vec::new();

    let pcl_constraints = build_pcl_constraints_from_py(pcl_dicts)?;
    let net_class_metadata = build_net_class_metadata_from_py(net_class_dicts)?;
    let comp_map = build_component_map_from_py_dict(component_map)?;
    let zone_map_resolved = build_zone_map_from_py_dict(zone_map)?;
    let topology = build_channel_topology_from_py(skeletons, channel_widths)?;

    let lattice = TypeLattice::new(net_class_metadata);

    let mut net_class_map: HashMap<usize, String> = HashMap::new();
    for (name, idx) in &comp_map {
        net_class_map.insert(*idx, name.clone());
    }

    let skeleton_edges: Vec<(usize, usize, String)> = {
        let mut edges = Vec::new();
        for item in skeletons {
            let d: Bound<'_, PyDict> = item.cast_into::<PyDict>()?;
            let na: usize = extract_str(&d, "net_a")
                .or_else(|_| extract_str(&d, "net1"))?
                .parse()
                .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(format!("{e}")))?;
            let nb: usize = extract_str(&d, "net_b")
                .or_else(|_| extract_str(&d, "net2"))?
                .parse()
                .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(format!("{e}")))?;
            let ch_id: String = extract_str(&d, "channel_id")
                .or_else(|_| extract_str(&d, "channel"))?;
            edges.push((na, nb, ch_id));
        }
        edges
    };

    let (inferred, lattice_warnings) = crate::type_lattice::propagate_through_topology(
        &skeleton_edges,
        &net_class_map,
        &lattice,
        None,
    );
    warnings.extend(lattice_warnings);

    let inferred_pcl = crate::desugar_tier0::compile_lattice_inferred_to_tier0(
        &inferred,
        &lattice,
    );

    let model = PclConstraintModel::new(pcl_constraints, inferred_pcl);
    let resolver = HashMapResolver {
        component_map: comp_map,
        zone_map: zone_map_resolved,
    };

    let mut prov = ProvenanceMap::new();

    let tier1_model = compile_tier0_to_tier1(&model, &resolver, &resolver, &mut prov)
        .map_err(|e| {
            PyErr::new::<pyo3::exceptions::PyValueError, _>(format!("Tier 0→1 error: {e}"))
        })?;

    let conflicts = detect_conflicts(&tier1_model.constraints);
    let conflict_dicts: Vec<Py<PyAny>> = conflicts
        .iter()
        .map(|c| {
            let d = PyDict::new(py);
            d.set_item("pcl_constraint_ids", c.pcl_constraint_ids.clone())?;
            d.set_item("description", &c.description)?;
            d.set_item("tier", format!("{}", c.tier))?;
            Ok(d.into())
        })
        .collect::<PyResult<Vec<_>>>()?;

    let tier2_constraints = compile_tier1_to_tier2(&tier1_model, &topology, &mut prov)
        .map_err(|e| {
            PyErr::new::<pyo3::exceptions::PyValueError, _>(format!("Tier 1→2 error: {e}"))
        })?;

    let constraint_dicts: Vec<Py<PyAny>> = tier2_constraints
        .iter()
        .map(|c| internal_constraint_to_py_dict(py, c))
        .collect::<Result<Vec<_>, _>>()?;

    let result = PyDict::new(py);
    result.set_item("constraints", constraint_dicts)?;
    result.set_item("warnings", warnings)?;
    result.set_item("conflicts", conflict_dicts)?;
    result.set_item("num_lowered", tier2_constraints.len())?;

    Ok(result.into())
}
