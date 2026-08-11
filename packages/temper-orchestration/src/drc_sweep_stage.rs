// The D6 `DRCSweepStage` + `TrackDeduplicationStage` +
// `ShortCircuitDetectionStage` of the Rust Orchestration Engine plan
// (2026-08-09-001, Phase D batch D6): `Stage<BoardState>` implementors
// mirroring `deterministic/stages/drc_sweep.py`.
//
// The whole run() orchestration moves to Rust: the state guards, the
// isinstance filters, the oracle call-backs (can_place_track_segment /
// get_valid_via_sites), the track/via rebuild with the pass-through of
// non-Trace route entries, the removed-nets accounting, the print(...)
// messages and the routes/vias frozenset writes; the track-dedup marshalling
// (Trace-only, marshalled-index -> route-index remap) and rebuild; the
// short-circuit pin_net_map build (CPython `round(x, 2)` keys) and the
// endpoint short sweep.
//
// What stays Python / single-source (driven through FFI, bit-exact by
// construction):
// - the DRCOracle methods and the `LAYER_NAME_TO_IDX` constant,
// - the temper-drc-rs `deduplicate_traces_py` kernel,
// - `core.pin_geometry.pin_world_position_at`, the Trace/Via pyclasses,
//   `core.board.STANDARD_LAYER_ORDER`,
// - CPython `round(x, 2)`, `sorted`, `str.format` and `print` (the
//   round-half-to-even keys and the `{px:.1f}` message rendering stay CPython).

use std::borrow::Cow;

use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList, PyTuple};

use crate::board_state::BoardState;
use crate::d6_util;
use crate::derivation_stage::{pyerr_stage, stage_guard};
use crate::grid_hv::getattr_default;
use crate::stage::{Stage, StageError};

const STAGE_NAME: &str = "drc_sweep";
const STAGE_NAME_DEDUP: &str = "track_deduplication";
const STAGE_NAME_SHORT: &str = "short_circuit_detection";

/// The post-routing DRC sweep: `drc_oracle` + `routes` + `vias` -> filtered
/// `routes` / `vias` (tracks/vias that fail the oracle's placement checks
/// removed; non-Trace route entries pass through).
#[derive(Debug, Clone)]
pub struct DRCSweepStage {
    pub tolerance: f64,
}

impl Stage<BoardState> for DRCSweepStage {
    fn name(&self) -> Cow<'static, str> {
        Cow::Borrowed(STAGE_NAME)
    }

    fn run(&self, state: BoardState) -> Result<BoardState, StageError> {
        stage_guard(STAGE_NAME, || {
            Python::attach(|py| {
                let to_stage = |e: pyo3::PyErr| pyerr_stage(STAGE_NAME, e);
                self.run_inner(py, state).map_err(to_stage)
            })
        })
    }
}

impl DRCSweepStage {
    fn run_inner(&self, py: Python<'_>, state: BoardState) -> PyResult<BoardState> {
        let oracle = match &state.drc_oracle {
            Some(o) if o.bind(py).is_truthy()? => o.bind(py).clone(),
            _ => return Ok(state),
        };
        let routes = match &state.routes {
            Some(r) => r.bind(py).clone(),
            None => PyList::empty(py).into_any(),
        };
        let vias = match &state.vias {
            Some(v) => v.bind(py).clone(),
            None => PyList::empty(py).into_any(),
        };

        let builtins = py.import("builtins")?;
        let isinstance = builtins.getattr("isinstance")?;
        let board_mod = py.import("temper_placer.core.board")?;
        let trace_cls = board_mod.getattr("Trace")?;
        let via_cls = board_mod.getattr("Via")?;
        let layer_name_to_idx = board_mod.getattr("LAYER_NAME_TO_IDX")?;

        let mut removed_tracks: i64 = 0;
        let mut removed_vias: i64 = 0;
        let mut removed_nets: Vec<String> = Vec::new();

        let valid_traces = PyList::empty(py);
        for trace in routes.try_iter()? {
            let trace = trace?;
            let is_trace: bool = isinstance.call1((&trace, &trace_cls))?.extract()?;
            if !is_trace {
                valid_traces.append(&trace)?;
                continue;
            }
            let layer_idx = layer_name_to_idx.call_method1("get", (trace.getattr("layer")?, 0))?;
            let net_attr = trace.getattr("net")?;
            let net = if net_attr.is_truthy()? {
                net_attr.clone()
            } else {
                pyo3::types::PyString::new(py, "").into_any()
            };
            let kwargs = PyDict::new(py);
            kwargs.set_item("start", trace.getattr("start")?)?;
            kwargs.set_item("end", trace.getattr("end")?)?;
            kwargs.set_item("layer", &layer_idx)?;
            kwargs.set_item("net", &net)?;
            kwargs.set_item("width", trace.getattr("width")?)?;
            let result = oracle.call_method("can_place_track_segment", (), Some(&kwargs))?;
            let valid: bool = result.get_item(0)?.extract()?;
            if valid {
                valid_traces.append(&trace)?;
            } else {
                removed_tracks += 1;
                if net_attr.is_truthy()? {
                    let net_str: String = net_attr.str()?.to_string();
                    if !removed_nets.contains(&net_str) {
                        removed_nets.push(net_str);
                    }
                }
            }
        }

        let valid_vias = PyList::empty(py);
        for via in vias.try_iter()? {
            let via = via?;
            let is_via: bool = isinstance.call1((&via, &via_cls))?.extract()?;
            if !is_via {
                valid_vias.append(&via)?;
                continue;
            }
            let net_attr = via.getattr("net")?;
            let net = if net_attr.is_truthy()? {
                net_attr.clone()
            } else {
                pyo3::types::PyString::new(py, "").into_any()
            };
            let kwargs = PyDict::new(py);
            kwargs.set_item("position", via.getattr("position")?)?;
            kwargs.set_item("search_radius", 0.1)?;
            kwargs.set_item("net", &net)?;
            let sites = oracle.call_method("get_valid_via_sites", (), Some(&kwargs))?;
            if sites.is_truthy()? {
                valid_vias.append(&via)?;
            } else {
                removed_vias += 1;
                if net_attr.is_truthy()? {
                    let net_str: String = net_attr.str()?.to_string();
                    if !removed_nets.contains(&net_str) {
                        removed_nets.push(net_str);
                    }
                }
            }
        }

        if removed_tracks > 0 || removed_vias > 0 {
            let msg = d6_util::py_format(
                py,
                "DRCSweep: Removed {} tracks, {} vias",
                &[
                    removed_tracks.into_pyobject(py)?.into_any(),
                    removed_vias.into_pyobject(py)?.into_any(),
                ],
            )?;
            d6_util::py_print(py, &[msg])?;
            if !removed_nets.is_empty() {
                let mut sorted = removed_nets.clone();
                sorted.sort();
                let preview: Vec<String> = sorted.iter().take(10).cloned().collect();
                let nets_preview = preview.join(", ");
                let extra = if removed_nets.len() > 10 {
                    let more = removed_nets.len() - 10;
                    d6_util::py_format(py, " (+{} more)", &[more.into_pyobject(py)?.into_any()])?
                } else {
                    pyo3::types::PyString::new(py, "").into_any()
                };
                let msg = d6_util::py_format(
                    py,
                    "  Affected nets: {}",
                    &[nets_preview.into_pyobject(py)?.into_any()],
                )?;
                let combined = msg.add(&extra)?;
                d6_util::py_print(py, &[combined])?;
            }
        }

        let frozenset_cls = builtins.getattr("frozenset")?;
        let mut new_state = state;
        new_state.routes = Some(frozenset_cls.call1((&valid_traces,))?.into_any().unbind());
        new_state.vias = Some(frozenset_cls.call1((&valid_vias,))?.into_any().unbind());
        Ok(new_state)
    }
}

/// The track-dedup stage: `routes` -> `routes` (direction-normalised
/// round-half-to-even segment keys; non-Trace entries pass through).
#[derive(Debug, Clone)]
pub struct TrackDeduplicationStage {
    pub tolerance_mm: f64,
}

impl Stage<BoardState> for TrackDeduplicationStage {
    fn name(&self) -> Cow<'static, str> {
        Cow::Borrowed(STAGE_NAME_DEDUP)
    }

    fn run(&self, state: BoardState) -> Result<BoardState, StageError> {
        stage_guard(STAGE_NAME_DEDUP, || {
            Python::attach(|py| {
                let to_stage = |e: pyo3::PyErr| pyerr_stage(STAGE_NAME_DEDUP, e);
                self.run_inner(py, state).map_err(to_stage)
            })
        })
    }
}

impl TrackDeduplicationStage {
    fn run_inner(&self, py: Python<'_>, state: BoardState) -> PyResult<BoardState> {
        let routes = match &state.routes {
            Some(r) if r.bind(py).is_truthy()? => r.bind(py).clone(),
            _ => return Ok(state),
        };
        let builtins = py.import("builtins")?;
        let isinstance = builtins.getattr("isinstance")?;
        let trace_cls = py.import("temper_placer.core.board")?.getattr("Trace")?;

        // Marshal ONLY the Trace objects; the kernel's kept indices are
        // positions INTO this marshalled list. Non-Trace route entries are
        // never marshalled; record the marshalled -> state.routes remap.
        let marshalled = PyList::empty(py);
        let mut marshalled_to_route: Vec<usize> = Vec::new();
        for (route_index, trace) in routes.try_iter()?.enumerate() {
            let trace = trace?;
            let is_trace: bool = isinstance.call1((&trace, &trace_cls))?.extract()?;
            if is_trace {
                marshalled_to_route.push(route_index);
                let entry = PyTuple::new(
                    py,
                    [
                        trace.getattr("start")?.into_any(),
                        trace.getattr("end")?.into_any(),
                        trace.getattr("layer")?.into_any(),
                        trace.getattr("net")?.into_any(),
                    ],
                )?;
                marshalled.append(entry)?;
            }
        }

        let drc = py.import("temper_drc_rs")?;
        let result = drc.call_method1(
            "deduplicate_traces_py",
            (&marshalled, self.tolerance_mm),
        )?;
        let kept_indices = result.get_item(0)?;
        let duplicates: usize = result.get_item(1)?.extract()?;

        // kept_route_indices = {marshalled_to_route[i] for i in kept_indices}
        let mut kept_route_indices: Vec<usize> = Vec::new();
        for i in kept_indices.try_iter()? {
            let idx: usize = i?.extract()?;
            kept_route_indices.push(marshalled_to_route[idx]);
        }

        let unique_traces = PyList::empty(py);
        for (j, trace) in routes.try_iter()?.enumerate() {
            let trace = trace?;
            let is_trace: bool = isinstance.call1((&trace, &trace_cls))?.extract()?;
            if is_trace && !kept_route_indices.contains(&j) {
                continue;
            }
            unique_traces.append(&trace)?;
        }

        if duplicates > 0 {
            let msg = d6_util::py_format(
                py,
                "TrackDeduplication: Removed {} duplicate segments",
                &[duplicates.into_pyobject(py)?.into_any()],
            )?;
            d6_util::py_print(py, &[msg])?;
        }

        let frozenset_cls = builtins.getattr("frozenset")?;
        let mut new_state = state;
        new_state.routes = Some(frozenset_cls.call1((&unique_traces,))?.into_any().unbind());
        Ok(new_state)
    }
}

/// The short-circuit detection stage: `netlist` + `routes` + `placements` ->
/// `routes` (tracks whose endpoints touch a wrong-net pin removed).
#[derive(Debug, Clone)]
pub struct ShortCircuitDetectionStage {
    pub tolerance_mm: f64,
}

impl Stage<BoardState> for ShortCircuitDetectionStage {
    fn name(&self) -> Cow<'static, str> {
        Cow::Borrowed(STAGE_NAME_SHORT)
    }

    fn run(&self, state: BoardState) -> Result<BoardState, StageError> {
        stage_guard(STAGE_NAME_SHORT, || {
            Python::attach(|py| {
                let to_stage = |e: pyo3::PyErr| pyerr_stage(STAGE_NAME_SHORT, e);
                self.run_inner(py, state).map_err(to_stage)
            })
        })
    }
}

impl ShortCircuitDetectionStage {
    fn run_inner(&self, py: Python<'_>, state: BoardState) -> PyResult<BoardState> {
        let netlist = match &state.netlist {
            Some(nl) if nl.bind(py).is_truthy()? => nl.bind(py).clone(),
            _ => return Ok(state),
        };
        let routes = match &state.routes {
            Some(r) if r.bind(py).is_truthy()? => r.bind(py).clone(),
            _ => return Ok(state),
        };

        let builtins = py.import("builtins")?;
        let isinstance = builtins.getattr("isinstance")?;
        let round_fn = builtins.getattr("round")?;
        let board_mod = py.import("temper_placer.core.board")?;
        let trace_cls = board_mod.getattr("Trace")?;
        let standard_order = board_mod.getattr("STANDARD_LAYER_ORDER")?;
        let pin_geometry = py.import("temper_placer.core.pin_geometry")?;
        let pin_world_position_at = pin_geometry.getattr("pin_world_position_at")?;

        // pin_net_map[(round(x,2), round(y,2), layer)] = net.name
        let pin_net_map = PyDict::new(py);
        let comp_positions = PyDict::new(py);
        if let Some(placements) = &state.placements {
            for item in placements.bind(py).try_iter()? {
                let item = item?;
                comp_positions.set_item(item.get_item(0)?, item.get_item(1)?)?;
            }
        }
        // The loop-leaked `net` variable the oracle's SHORT message references
        // (the last net iterated while building the pin map, or the matching
        // net on a break -- both are the last-iterated net).
        let nets_obj = netlist.getattr("nets")?;
        let nets: Vec<Bound<'_, PyAny>> = nets_obj.try_iter()?.collect::<PyResult<Vec<_>>>()?;
        let mut leaked_net: Option<Bound<'_, PyAny>> = None;

        for comp in netlist.getattr("components")?.try_iter()? {
            let comp = comp?;
            let comp_ref = comp.getattr("ref")?;
            let comp_pos = if comp_positions.contains(&comp_ref)? {
                comp_positions.as_any().get_item(&comp_ref)?
            } else {
                let ip = comp.getattr("initial_position")?;
                if ip.is_truthy()? {
                    ip
                } else {
                    PyTuple::new(py, [0_i64.into_pyobject(py)?.into_any(), 0_i64.into_pyobject(py)?.into_any()])?.into_any()
                }
            };
            for pin in comp.getattr("pins")?.try_iter()? {
                let pin = pin?;
                let pin_pos = pin_world_position_at.call1((&pin, &comp, &comp_pos))?;
                for net in &nets {
                    leaked_net = Some(net.clone());
                    let pin_name = pin.getattr("name")?;
                    let pin_number = pin.getattr("number")?;
                    let hit_name = contains_pair(py, &comp_ref, &pin_name, net)?;
                    let hit_number = contains_pair(py, &comp_ref, &pin_number, net)?;
                    if hit_name || hit_number {
                        let px = round_fn.call1((pin_pos.get_item(0)?, 2))?;
                        let py_val = round_fn.call1((pin_pos.get_item(1)?, 2))?;
                        if pin.getattr("is_pth")?.extract::<bool>()? {
                            for layer in standard_order.try_iter()? {
                                let layer = layer?;
                                let key = PyTuple::new(
                                    py,
                                    [px.clone().into_any(), py_val.clone().into_any(), layer.str()?.into_any()],
                                )?;
                                pin_net_map.set_item(&key, net.getattr("name")?)?;
                            }
                        } else {
                            let layer = getattr_default(
                                py,
                                &pin,
                                "layer",
                                crate::grid_hv::str_py(py, "F.Cu"),
                            )?;
                            let key = PyTuple::new(
                                py,
                                [px.clone().into_any(), py_val.clone().into_any(), layer.into_any()],
                            )?;
                            pin_net_map.set_item(&key, net.getattr("name")?)?;
                        }
                        break;
                    }
                }
            }
        }

        let valid_traces = PyList::empty(py);
        let mut removed: i64 = 0;
        let tol = self.tolerance_mm;
        for trace in routes.try_iter()? {
            let trace = trace?;
            let is_trace: bool = isinstance.call1((&trace, &trace_cls))?.extract()?;
            if !is_trace {
                valid_traces.append(&trace)?;
                continue;
            }
            let track_net_attr = trace.getattr("net")?;
            let track_net = if track_net_attr.is_truthy()? {
                track_net_attr.str()?.to_string()
            } else {
                String::new()
            };
            let trace_layer = trace.getattr("layer")?;
            let mut is_short = false;

            for point_idx in 0..2 {
                let point = trace.getattr(if point_idx == 0 { "start" } else { "end" })?;
                let px = round_fn.call1((point.get_item(0)?, 2))?;
                let py_val = round_fn.call1((point.get_item(1)?, 2))?;
                let pxf: f64 = px.extract()?;
                let pyf: f64 = py_val.extract()?;
                let mut short_hit = false;
                for (key, pin_net) in pin_net_map.iter() {
                    let key_layer = key.get_item(2)?;
                    let same_layer: bool = key_layer.eq(&trace_layer)?;
                    if !same_layer {
                        continue;
                    }
                    let key_x: f64 = key.get_item(0)?.extract()?;
                    let key_y: f64 = key.get_item(1)?.extract()?;
                    let pin_net_str: String = pin_net.str()?.to_string();
                    if (pxf - key_x).abs() <= tol
                        && (pyf - key_y).abs() <= tol
                        && pin_net_str != track_net
                        && !track_net.is_empty()
                    {
                        let msg = d6_util::py_format(
                            py,
                            "  SHORT: {} track near {} pin at ({:.1f}, {:.1f})",
                            &[
                                track_net_attr.clone().into_any(),
                                leaked_net.as_ref().unwrap_or(&nets_obj).clone().into_any(),
                                px.into_any(),
                                py_val.into_any(),
                            ],
                        )?;
                        d6_util::py_print(py, &[msg])?;
                        short_hit = true;
                        break;
                    }
                }
                if short_hit {
                    is_short = true;
                    break;
                }
            }

            if !is_short {
                valid_traces.append(&trace)?;
            } else {
                removed += 1;
            }
        }

        if removed > 0 {
            let msg = d6_util::py_format(
                py,
                "ShortCircuitDetection: Removed {} shorting tracks",
                &[removed.into_pyobject(py)?.into_any()],
            )?;
            d6_util::py_print(py, &[msg])?;
        }

        let frozenset_cls = builtins.getattr("frozenset")?;
        let mut new_state = state;
        new_state.routes = Some(frozenset_cls.call1((&valid_traces,))?.into_any().unbind());
        Ok(new_state)
    }
}

/// `(ref, pin) in net.pins` -- membership via CPython `in` on the pins list.
fn contains_pair<'py>(
    py: Python<'py>,
    comp_ref: &Bound<'py, PyAny>,
    pin_name: &Bound<'py, PyAny>,
    net: &Bound<'py, PyAny>,
) -> PyResult<bool> {
    let pair = PyTuple::new(py, [comp_ref.clone().into_any(), pin_name.clone().into_any()])?;
    let pins = net.getattr("pins")?;
    pins.call_method1("__contains__", (&pair,))?.extract()
}

/// FFI entry for the Python shim: `run_drc_sweep(state, tolerance)`.
#[pyfunction]
pub fn run_drc_sweep(
    py: Python<'_>,
    state: Py<PyAny>,
    tolerance: f64,
) -> PyResult<Py<PyAny>> {
    let rust_state = crate::d1_bridge::from_python(py, state.bind(py)).map_err(|e| {
        pyo3::exceptions::PyRuntimeError::new_err(format!("{STAGE_NAME}: {e}"))
    })?;
    let stage = DRCSweepStage { tolerance };
    let out = stage.run(rust_state).map_err(|e| crate::config_attach_stage::to_pyerr(&e))?;
    crate::d1_bridge::to_python(py, state.bind(py), &out, &["routes", "vias"])
}

/// FFI entry for the Python shim: `run_track_deduplication(state,
/// tolerance_mm)`.
#[pyfunction]
pub fn run_track_deduplication(
    py: Python<'_>,
    state: Py<PyAny>,
    tolerance_mm: f64,
) -> PyResult<Py<PyAny>> {
    let rust_state = crate::d1_bridge::from_python(py, state.bind(py)).map_err(|e| {
        pyo3::exceptions::PyRuntimeError::new_err(format!("{STAGE_NAME_DEDUP}: {e}"))
    })?;
    let stage = TrackDeduplicationStage { tolerance_mm };
    let out = stage.run(rust_state).map_err(|e| crate::config_attach_stage::to_pyerr(&e))?;
    crate::d1_bridge::to_python(py, state.bind(py), &out, &["routes"])
}

/// FFI entry for the Python shim: `run_short_circuit_detection(state,
/// tolerance_mm)`.
#[pyfunction]
pub fn run_short_circuit_detection(
    py: Python<'_>,
    state: Py<PyAny>,
    tolerance_mm: f64,
) -> PyResult<Py<PyAny>> {
    let rust_state = crate::d1_bridge::from_python(py, state.bind(py)).map_err(|e| {
        pyo3::exceptions::PyRuntimeError::new_err(format!("{STAGE_NAME_SHORT}: {e}"))
    })?;
    let stage = ShortCircuitDetectionStage { tolerance_mm };
    let out = stage.run(rust_state).map_err(|e| crate::config_attach_stage::to_pyerr(&e))?;
    crate::d1_bridge::to_python(py, state.bind(py), &out, &["routes"])
}
