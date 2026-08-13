// The D1 `DrcOracleSetupStage` + `NetClassSetupStage` of the Rust
// Orchestration Engine plan (2026-08-09-001, Phase D batch D1): `Stage<
// BoardState>` implementors mirroring `deterministic/stages/setup.py`.
//
// `DrcOracleSetupStage.run` reproduces the Python orchestration exactly:
// choose the ClearanceMatrix source (design_rules object vs `state.board`
// parse vs default), create the `DRCOracle` Python object, register pads
// (parsed_pads branch, then the board+netlist fallback), rebuild the
// geometry index, and write `drc_oracle` back into BoardState. The leaf
// objects -- ClearanceMatrix, DRCOracle, Pad, Point, NetClassRules,
// `pin_world_position` -- are Python classes whose numeric bodies are
// already Rust kernels (temper-drc-rs / temper-geometry); this stage keeps
// thin Python delegation for that genuinely-Python object glue while the
// orchestration (branching, iteration, layer mapping, PTH detection, shape
// normalization, net sentinel) lives in Rust.
//
// `NetClassSetupStage` reads the netlist and applies the net-class mapping
// via the already-Rust `Netlist.apply_net_class_mapping` pyclass method
// (netlist is mutated in place; the stage returns the state unchanged).

#[cfg(feature = "python")]
use std::borrow::Cow;

#[cfg(feature = "python")]
use pyo3::exceptions::PyAttributeError;
#[cfg(feature = "python")]
use pyo3::prelude::*;
#[cfg(feature = "python")]
use pyo3::types::{PyDict, PyTuple};

#[cfg(feature = "python")]
use crate::board_state::BoardState;
#[cfg(feature = "python")]
use crate::config_attach_stage::to_pyerr;
#[cfg(feature = "python")]
use crate::derivation_stage::{pyerr_stage, stage_guard};
#[cfg(feature = "python")]
use crate::stage::{Stage, StageError};
#[cfg(feature = "python")]
use temper_data_model::{PlacementSet};

#[cfg(feature = "python")]
/// The DRC-oracle setup stage: design_rules/board -> populated DRCOracle.
#[derive(Debug, Clone)]
pub struct DrcOracleSetupStage {
    pub design_rules: Option<Py<PyAny>>,
    pub parsed_pads: Option<Py<PyAny>>,
}

#[cfg(feature = "python")]
impl Stage<BoardState> for DrcOracleSetupStage {
    fn name(&self) -> Cow<'static, str> {
        Cow::Borrowed("drc_oracle_setup")
    }

    fn run(&self, state: BoardState) -> Result<BoardState, StageError> {
        stage_guard("drc_oracle_setup", || {
            Python::attach(|py| {
                let to_stage = |e: pyo3::PyErr| pyerr_stage("drc_oracle_setup", e);
                let matrix = build_matrix(py, &self.design_rules, &state).map_err(to_stage)?;
                let oracle_cls = py
                    .import("temper_placer.router_v6.constraints_drc_oracle")
                    .map_err(to_stage)?
                    .getattr("DRCOracle")
                    .map_err(to_stage)?;
                let oracle = oracle_cls.call1((matrix,)).map_err(to_stage)?;

                if let Some(parsed_pads) = &self.parsed_pads {
                    register_parsed_pads(py, &oracle, parsed_pads).map_err(to_stage)?;
                    oracle
                        .getattr("geometry")
                        .map_err(to_stage)?
                        .call_method0("rebuild_index")
                        .map_err(to_stage)?;
                } else if state.board.is_some() && state.netlist.is_some() {
                    register_netlist_pads(py, &oracle, &state).map_err(to_stage)?;
                    oracle
                        .getattr("geometry")
                        .map_err(to_stage)?
                        .call_method0("rebuild_index")
                        .map_err(to_stage)?;
                }

                let mut new_state = state;
                new_state.drc_oracle = Some(oracle.into_any().unbind());
                Ok(new_state)
            })
        })
    }
}

#[cfg(feature = "python")]
/// `NetClassSetupStage`: apply the net-class mapping early in the pipeline.
#[derive(Debug, Clone)]
pub struct NetClassSetupStage {
    pub net_classes: Option<Py<PyAny>>,
}

#[cfg(feature = "python")]
impl Stage<BoardState> for NetClassSetupStage {
    fn name(&self) -> Cow<'static, str> {
        Cow::Borrowed("net_class_setup")
    }

    fn run(&self, state: BoardState) -> Result<BoardState, StageError> {
        stage_guard("net_class_setup", || {
            Python::attach(|py| {
                let to_stage = |e: pyo3::PyErr| pyerr_stage("net_class_setup", e);
                let netlist = match &state.netlist {
                    Some(n) => n.clone_ref(py),
                    None => return Ok(state),
                };
                let net_classes = match &self.net_classes {
                    Some(nc) => nc.clone_ref(py),
                    None => return Ok(state),
                };
                // `if not self.net_classes`: an empty mapping is skipped.
                if net_classes.bind(py).len().map_err(to_stage)? == 0 {
                    return Ok(state);
                }
                let _updated: i64 = netlist
                    .bind(py)
                    .call_method1("apply_net_class_mapping", (net_classes,))
                    .map_err(to_stage)?
                    .extract()
                    .map_err(to_stage)?;
                Ok(state)
            })
        })
    }
}

#[cfg(feature = "python")]
/// FFI entry for the Python shim: `run_drc_oracle_setup(state,
/// design_rules, parsed_pads)`.
#[pyfunction]
#[pyo3(signature = (state, design_rules=None, parsed_pads=None))]
pub fn run_drc_oracle_setup(
    py: Python<'_>,
    state: Py<PyAny>,
    design_rules: Option<Py<PyAny>>,
    parsed_pads: Option<Py<PyAny>>,
) -> PyResult<Py<PyAny>> {
    let rust_state = crate::d1_bridge::from_python(py, state.bind(py)).map_err(|e| {
        pyo3::exceptions::PyRuntimeError::new_err(format!("drc_oracle_setup: {e}"))
    })?;
    let stage = DrcOracleSetupStage {
        design_rules,
        parsed_pads,
    };
    let out = stage.run(rust_state).map_err(|e| to_pyerr(&e))?;
    crate::d1_bridge::to_python(py, state.bind(py), &out, &["drc_oracle"])
}

#[cfg(feature = "python")]
/// FFI entry for the Python shim: `run_net_class_setup(state, net_classes)`.
#[pyfunction]
#[pyo3(signature = (state, net_classes=None))]
pub fn run_net_class_setup(
    py: Python<'_>,
    state: Py<PyAny>,
    net_classes: Option<Py<PyAny>>,
) -> PyResult<Py<PyAny>> {
    let rust_state = crate::d1_bridge::from_python(py, state.bind(py)).map_err(|e| {
        pyo3::exceptions::PyRuntimeError::new_err(format!("net_class_setup: {e}"))
    })?;
    let stage = NetClassSetupStage { net_classes };
    let out = stage.run(rust_state).map_err(|e| to_pyerr(&e))?;
    // The netlist is mutated in place (shared Py object); nothing is
    // written back, so the original Python state object is returned.
    crate::d1_bridge::to_python(py, state.bind(py), &out, &[])
}

// ---------------------------------------------------------------------------
// ClearanceMatrix construction
// ---------------------------------------------------------------------------

#[cfg(feature = "python")]
/// The `run()` matrix branch: design_rules object -> populated
/// ClearanceMatrix, else `ClearanceMatrix.parse(state.board)`, else
/// `DesignRulesParser.create_default()`.
fn build_matrix<'py>(
    py: Python<'py>,
    design_rules: &Option<Py<PyAny>>,
    state: &BoardState,
) -> PyResult<Bound<'py, PyAny>> {
    let cdr = py.import("temper_placer.router_v6.constraints_design_rules")?;
    if let Some(dr) = design_rules {
        let dr = dr.bind(py);
        let matrix = cdr.getattr("ClearanceMatrix")?.call0()?;
        if dr.hasattr("net_class_rules")? {
            // PlacementConstraints (config) duck-typed branch.
            let ncr_cls = py
                .import("temper_placer.core.design_rules")?
                .getattr("NetClassRules")?;
            for (name, rules) in dict_items(py, &dr.getattr("net_class_rules")?)? {
                let _ = name;
                let rules = rules.bind(py);
                let kwargs = PyDict::new(py);
                kwargs.set_item("name", rules.getattr("name")?)?;
                kwargs.set_item("trace_width", rules.getattr("trace_width_mm")?)?;
                kwargs.set_item("clearance", rules.getattr("clearance_mm")?)?;
                kwargs.set_item("via_diameter", rules.getattr("via_size_mm")?)?;
                kwargs.set_item("via_drill", rules.getattr("via_drill_mm")?)?;
                kwargs.set_item("via_template", rules.getattr("via_template")?)?;
                kwargs.set_item("creepage_mm", rules.getattr("creepage_mm")?)?;
                let dru_priority = getattr_default(py, rules, "dru_priority", py_int(py, 0))?;
                kwargs.set_item("dru_priority", dru_priority)?;
                let ncr = ncr_cls.call((), Some(&kwargs))?;
                matrix.call_method1("add_net_class_rules", (ncr,))?;
            }
            for (net, class_name) in dict_items(py, &dr.getattr("net_classes")?)? {
                matrix.call_method1("set_net_class", (net, class_name))?;
            }
        } else {
            // DesignRules object branch.
            for (_name, rules) in dict_items(py, &dr.getattr("net_classes")?)? {
                matrix.call_method1("add_net_class_rules", (rules,))?;
            }
            for (net_name, net_class_name) in dict_items(py, &dr.getattr("net_class_assignments")?)? {
                matrix.call_method1("set_net_class", (net_name, net_class_name))?;
            }
        }
        if dr.hasattr("differential_pairs")? && dr.getattr("differential_pairs")?.is_truthy()? {
            let pairs = dr.getattr("differential_pairs")?;
            for pair in pairs.try_iter()? {
                let pair = pair?;
                matrix.call_method1(
                    "add_differential_pair",
                    (pair.getattr("net_pos")?, pair.getattr("net_neg")?, pair.getattr("spacing_mm")?),
                )?;
            }
        }
        return Ok(matrix);
    }
    if let Some(board) = &state.board {
        let matrix = cdr
            .getattr("ClearanceMatrix")?
            .call_method1("parse", (board.bind(py),))?;
        return Ok(matrix);
    }
    let parser = cdr.getattr("DesignRulesParser")?;
    parser.getattr("create_default")?.call0()
}

// ---------------------------------------------------------------------------
// Pad registration
// ---------------------------------------------------------------------------

#[cfg(feature = "python")]
/// `if self.parsed_pads:` branch -- register pads from PadData objects.
fn register_parsed_pads(
    py: Python<'_>,
    oracle: &Bound<'_, PyAny>,
    parsed_pads: &Py<PyAny>,
) -> PyResult<()> {
    let pad_cls = py
        .import("temper_placer.router_v6.constraints_spatial_index")?
        .getattr("Pad")?;
    let point_cls = py
        .import("temper_placer.router_v6.constraints_geometry")?
        .getattr("Point")?;

    for pad_data in parsed_pads.bind(py).try_iter()? {
        let pad_data = pad_data?;
        let pad_layer: String = getattr_default(py, &pad_data, "layer", str_py(py, "F.Cu"))?
            .extract()?;
        let drill = getattr_default(py, &pad_data, "drill", py.None())?;
        let has_drill = drill_has_hole(py, &drill)?;
        let is_pth = pad_layer == "all" || pad_layer == "*.Cu" || has_drill;

        let layer_idx = match pad_layer.as_str() {
            "B.Cu" => 3,
            "In1.Cu" => 1,
            "In2.Cu" => 2,
            _ => 0,
        };

        let net = getattr_default(py, &pad_data, "net", py.None())?;
        let pad_net: String = if net.is_none() || net.eq(str_py(py, "").bind(py))? {
            "__UNCONNECTED__".to_string()
        } else {
            net.extract()?
        };

        let shape_raw: String = getattr_default(py, &pad_data, "shape", str_py(py, "rect"))?
            .extract()?;
        let shape = if ["circle", "rect", "oval"].contains(&shape_raw.as_str()) {
            shape_raw
        } else {
            "rect".to_string()
        };

        let position = pad_data.getattr("position")?;
        let x: f64 = position.get_item(0)?.extract()?;
        let y: f64 = position.get_item(1)?.extract()?;
        let center = point_cls.call1((x, y))?;

        let component_ref: String = pad_data.getattr("component_ref")?.extract()?;
        let number: String = pad_data.getattr("number")?.extract()?;
        let id = format!("{component_ref}.{number}");
        let rotation: f64 = getattr_default(py, &pad_data, "rotation", py_float(py, 0.0))?.extract()?;

        let pad = build_pad(
            py,
            &pad_cls,
            &center,
            &shape,
            &pad_data.getattr("size")?,
            &pad_net,
            layer_idx,
            &id,
            rotation,
            0.1,
            is_pth,
        )?;
        oracle.call_method1("register_pad", (pad,))?;
    }
    Ok(())
}

#[cfg(feature = "python")]
/// `elif state.board and state.netlist:` branch -- register pads computed
/// from netlist components/pins.
fn register_netlist_pads(
    py: Python<'_>,
    oracle: &Bound<'_, PyAny>,
    state: &BoardState,
) -> PyResult<()> {
    let pad_cls = py
        .import("temper_placer.router_v6.constraints_spatial_index")?
        .getattr("Pad")?;
    let point_cls = py
        .import("temper_placer.router_v6.constraints_geometry")?
        .getattr("Point")?;
    let pin_world_position = py
        .import("temper_placer.core.pin_geometry")?
        .getattr("pin_world_position")?;

    // placements_dict = dict(state.placements) if state.placements else {}
    // U6 (O-C3) group-2: the owned `PlacementSet` is rebuilt into the Python
    // frozenset, then `dict(...)`-ed exactly like the oracle.
    let placements: Py<PyAny> = match &state.placements {
        Some(p) if !p.is_empty() => crate::marshal::to_python::<PlacementSet>(py, p)?,
        _ => py.None(),
    };
    let placements_dict: Py<PyAny> = if !placements.is_none(py) {
        py.import("builtins")?
            .getattr("dict")?
            .call1((placements,))?
            .into_any()
            .unbind()
    } else {
        py.None()
    };

    let netlist = state.netlist.as_ref().ok_or_else(|| {
        pyo3::exceptions::PyValueError::new_err("netlist field missing in netlist fallback")
    })?;
    let components = netlist.bind(py).getattr("components")?;
    for component in components.try_iter()? {
        let component = component?;
        // pos = placements_dict.get(component.ref, component.initial_position)
        let pos: Py<PyAny> = if !placements_dict.is_none(py) {
            let get = placements_dict.bind(py).getattr("get")?;
            get.call1((
                component.getattr("ref")?,
                component.getattr("initial_position")?,
            ))?
            .into_any()
            .unbind()
        } else {
            component.getattr("initial_position")?.into_any().unbind()
        };
        if pos.is_none(py) {
            continue;
        }

        let rot_idx: i64 = {
            let rot = getattr_default(py, &component, "initial_rotation_quadrant", py.None())?;
            if rot.is_none() {
                0
            } else {
                rot.extract()?
            }
        };
        let rotation = rot_idx as f64 * 90.0;

        let pins = component.getattr("pins")?;
        for pin in pins.try_iter()? {
            let pin = pin?;
            let pin_pos = pin_world_position.call1((&pin, &component))?;
            let x: f64 = pin_pos.get_item(0)?.extract()?;
            let y: f64 = pin_pos.get_item(1)?.extract()?;
            let center = point_cls.call1((x, y))?;

            let pin_layer: String = getattr_default(py, &pin, "layer", str_py(py, "F.Cu"))?
                .extract()?;
            let is_pth: bool = {
                let is_pth_attr: bool = getattr_default(py, &pin, "is_pth", py_bool(py, false))?
                    .extract()?;
                pin_layer == "all" || is_pth_attr
            };
            let layer_idx = match pin_layer.as_str() {
                "B.Cu" => 3,
                "In1.Cu" => 1,
                "In2.Cu" => 2,
                _ => 0,
            };

            let net = getattr_default(py, &pin, "net", py.None())?;
            let pad_net: String = if net.is_none() || net.eq(str_py(py, "").bind(py))? {
                "__UNCONNECTED__".to_string()
            } else {
                net.extract()?
            };

            let shape_raw: String =
                getattr_default(py, &pin, "shape", str_py(py, "rect"))?.extract()?;
            let shape = if ["circle", "rect", "oval"].contains(&shape_raw.as_str()) {
                shape_raw
            } else {
                "rect".to_string()
            };

            let width: f64 = getattr_default(py, &pin, "width", py_float(py, 1.0))?.extract()?;
            let height: f64 = getattr_default(py, &pin, "height", py_float(py, 1.0))?.extract()?;
            let size = PyTuple::new(py, [width, height])?;

            let component_ref: String = component.getattr("ref")?.extract()?;
            let number: String = pin.getattr("number")?.extract()?;
            let id = format!("{component_ref}.{number}");

            let mask_expansion: f64 =
                getattr_default(py, &pin, "mask_expansion", py_float(py, 0.1))?.extract()?;

            let pad = build_pad(
                py,
                &pad_cls,
                &center,
                &shape,
                &size.into_any(),
                &pad_net,
                layer_idx,
                &id,
                rotation,
                mask_expansion,
                is_pth,
            )?;
            oracle.call_method1("register_pad", (pad,))?;
        }
    }
    Ok(())
}

// ---------------------------------------------------------------------------
// Python-object helpers
// ---------------------------------------------------------------------------

#[cfg(feature = "python")]
/// Construct a `Pad` Python object with the same kwargs the Python shim
/// used (`constraints_spatial_index.Pad` dataclass).
#[allow(clippy::too_many_arguments)]
fn build_pad<'py>(
    py: Python<'py>,
    pad_cls: &Bound<'py, PyAny>,
    center: &Bound<'py, PyAny>,
    shape: &str,
    size: &Bound<'py, PyAny>,
    net: &str,
    layer: i64,
    id: &str,
    rotation: f64,
    mask_expansion: f64,
    is_pth: bool,
) -> PyResult<Bound<'py, PyAny>> {
    let kwargs = PyDict::new(py);
    kwargs.set_item("center", center)?;
    kwargs.set_item("shape", shape)?;
    kwargs.set_item("size", size)?;
    kwargs.set_item("net", net)?;
    kwargs.set_item("layer", layer)?;
    kwargs.set_item("id", id)?;
    kwargs.set_item("rotation", rotation)?;
    kwargs.set_item("mask_expansion", mask_expansion)?;
    kwargs.set_item("is_pth", is_pth)?;
    pad_cls.call((), Some(&kwargs))
}

#[cfg(feature = "python")]
/// `getattr(obj, name, default)` with AttributeError fallback.
fn getattr_default<'py>(
    py: Python<'py>,
    obj: &Bound<'py, PyAny>,
    name: &str,
    default: Py<PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    match obj.getattr(name) {
        Ok(v) => Ok(v),
        Err(e) if e.is_instance_of::<PyAttributeError>(py) => Ok(default.bind(py).clone()),
        Err(e) => Err(e),
    }
}

#[cfg(feature = "python")]
/// Iterate a dict's items in insertion order, returning owned `(key,
/// value)` pairs.
fn dict_items(
    py: Python<'_>,
    dict: &Bound<'_, PyAny>,
) -> PyResult<Vec<(Py<PyAny>, Py<PyAny>)>> {
    let mut out = Vec::new();
    let items = dict.call_method0("items")?;
    for item in items.try_iter()? {
        let item = item?;
        let key = item.get_item(0)?;
        let value = item.get_item(1)?;
        out.push((key.unbind(), value.unbind()));
    }
    let _ = py;
    Ok(out)
}

#[cfg(feature = "python")]
/// The Python `drill is not None and ((isinstance(drill, (int, float)) and
/// drill > 0) or (hasattr(drill, "diameter") and drill.diameter and
/// drill.diameter > 0))` PTH test.
fn drill_has_hole(py: Python<'_>, drill: &Bound<'_, PyAny>) -> PyResult<bool> {
    if drill.is_none() {
        return Ok(false);
    }
    // isinstance(drill, (int, float)) and drill > 0
    if drill.is_instance(&py.get_type::<pyo3::types::PyInt>())?
        || drill.is_instance(&py.get_type::<pyo3::types::PyFloat>())?
    {
        let v: f64 = drill.extract()?;
        if v > 0.0 {
            return Ok(true);
        }
    }
    // hasattr(drill, "diameter") and drill.diameter and drill.diameter > 0
    if drill.hasattr("diameter")? {
        let diameter = drill.getattr("diameter")?;
        if !diameter.is_none() && diameter.is_truthy()? {
            let v: f64 = diameter.extract()?;
            if v > 0.0 {
                return Ok(true);
            }
        }
    }
    Ok(false)
}

#[cfg(feature = "python")]
fn str_py(py: Python<'_>, s: &str) -> Py<PyAny> {
    pyo3::types::PyString::new(py, s).into_any().unbind()
}

#[cfg(feature = "python")]
fn py_float(py: Python<'_>, f: f64) -> Py<PyAny> {
    pyo3::types::PyFloat::new(py, f).into_any().unbind()
}

#[cfg(feature = "python")]
fn py_int(py: Python<'_>, i: i64) -> Py<PyAny> {
    i.into_pyobject(py)
        .map(|b| b.into_any().unbind())
        .unwrap_or_else(|_| py.None())
}

#[cfg(feature = "python")]
fn py_bool(py: Python<'_>, b: bool) -> Py<PyAny> {
    let name = if b { "True" } else { "False" };
    py.import("builtins")
        .and_then(|m| m.getattr(name))
        .map(|bound| bound.into_any().unbind())
        .unwrap_or_else(|_| py.None())
}
