// The D6 `ViaValidationStage` + `ViaDeduplicationStage` of the Rust
// Orchestration Engine plan (2026-08-09-001, Phase D batch D6):
// `Stage<BoardState>` implementors mirroring
// `deterministic/stages/via_validation.py`.
//
// The whole run() orchestration moves to Rust: the state guards, the
// trace-endpoint index (with the 0.5mm mid-trace sampling), the pin-position
// index (with the PTH all-layers registration), the per-via validity sweep
// (the diff-pair skip, the plane-net special case, the `_count_connected_layers`
// delegation), the `print(...)` messages and the `vias=frozenset(...)` write;
// `ViaDeduplicationStage` runs the position-dedup sweep and the frozenset
// write.
//
// What stays Python / single-source (driven through FFI, bit-exact by
// construction):
// - the temper-drc-rs `count_connected_layers_py` / `dedup_via_positions_py`
//   kernels,
// - `core.net_classification.is_ground_net` / `is_power_net` (the plane-net
//   predicate, via temper-io-types),
// - `core.pin_geometry.pin_world_position`, the `Trace` / `Via` pyclasses and
//   the `core.board` layer constants,
// - `print` / `str.format` for every interpolated message (David-Gay and
//   tuple-repr rendering) and `sorted` for the removed-net preview.

#[cfg(feature = "python")]
use std::borrow::Cow;

#[cfg(feature = "python")]
use pyo3::prelude::*;
#[cfg(feature = "python")]
use pyo3::types::{PyDict, PyList, PyTuple};

#[cfg(feature = "python")]
use std::collections::HashSet;

#[cfg(feature = "python")]
use crate::board_state::{BoardState, RouteEntry, ViaEntry};
#[cfg(feature = "python")]
use crate::d6_util;
#[cfg(feature = "python")]
use crate::derivation_stage::{pyerr_stage, stage_guard};
#[cfg(feature = "python")]
use crate::grid_hv::getattr_default;
#[cfg(feature = "python")]
use crate::host_math;
#[cfg(feature = "python")]
use crate::stage::{Stage, StageError};

const STAGE_NAME: &str = "via_validation";
const STAGE_NAME_DEDUP: &str = "via_deduplication";
const DEFAULT_LAYER: &str = "F.Cu";

/// The via-cleanup stage: `routes` + `vias` + `netlist` -> `vias` (dangling
/// vias removed, plane-net and diff-pair vias preserved).
#[derive(Debug, Clone)]
pub struct ViaValidationStage {
    pub tolerance_mm: f64,
    pub require_both_layers: bool,
}

#[cfg(feature = "python")]
impl Stage<BoardState> for ViaValidationStage {
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

#[cfg(feature = "python")]
impl ViaValidationStage {
    fn run_inner(&self, py: Python<'_>, state: BoardState) -> PyResult<BoardState> {
        // `if not state.vias or not state.routes: return state` — the
        // truthiness guards map to `!set.is_empty()`, the owned sets are
        // rebuilt into the Python frozensets the oracle loops expect.
        let vias = match &state.vias {
            Some(v) if !v.is_empty() => crate::marshal::to_python::<HashSet<ViaEntry>>(py, v)?.into_bound(py),
            _ => return Ok(state),
        };
        let routes = match &state.routes {
            Some(r) if !r.is_empty() => {
                crate::marshal::to_python::<HashSet<RouteEntry>>(py, r)?.into_bound(py)
            }
            _ => return Ok(state),
        };

        let trace_index = self.build_trace_endpoint_index(py, &routes)?;
        let pin_index = self.build_pin_position_index(py, &state)?;

        let builtins = py.import("builtins")?;
        let net_classify = py.import("temper_placer.core.net_classification")?;
        let board_mod = py.import("temper_placer.core.board")?;
        let plane_layer_indices = board_mod.getattr("PLANE_LAYER_INDICES")?;
        let drc = py.import("temper_drc_rs")?;

        let valid_vias = PyList::empty(py);
        let mut removed_count: i64 = 0;
        let mut removed_nets: Vec<String> = Vec::new();
        let mut plane_vias_total: i64 = 0;
        let mut plane_vias_kept: i64 = 0;
        let plane_vias_removed = PyList::empty(py);

        for via in vias.try_iter()? {
            let via = via?;
            // `getattr(via, "is_diff_pair", False)` -> skip protected diff vias.
            let is_diff_pair: bool = match via.getattr("is_diff_pair") {
                Ok(v) => v.extract()?,
                Err(e) if e.is_instance_of::<pyo3::exceptions::PyAttributeError>(py) => false,
                Err(e) => return Err(e),
            };            if is_diff_pair {
                valid_vias.append(&via)?;
                continue;
            }

            let net = via.getattr("net")?;
            let is_plane = if net.is_truthy()? {
                is_plane_net(py, &net, &net_classify)?
            } else {
                false
            };
            if is_plane {
                plane_vias_total += 1;
            }

            let layers_connected = self.count_connected_layers(
                py,
                &via,
                &trace_index,
                &pin_index,
                &plane_layer_indices,
                &drc,
            )?;

            let is_valid = if self.require_both_layers {
                layers_connected >= 2
            } else {
                layers_connected >= 1
            };

            if is_valid {
                valid_vias.append(&via)?;
                if is_plane {
                    plane_vias_kept += 1;
                }
            } else if is_plane && layers_connected >= 1 {
                // Plane vias with one F.Cu connection are valid (inner pours).
                valid_vias.append(&via)?;
                plane_vias_kept += 1;
            } else {
                removed_count += 1;
                if net.is_truthy()? {
                    let net_str: String = net.str()?.to_string();
                    if !removed_nets.contains(&net_str) {
                        removed_nets.push(net_str);
                    }
                }
                if is_plane {
                    let pos = via.getattr("position")?;
                    let layers = via.getattr("layers")?;
                    let entry = PyTuple::new(
                        py,
                        [
                            net.into_any(),
                            pos.into_any(),
                            layers.into_any(),
                            layers_connected.into_pyobject(py)?.into_any(),
                        ],
                    )?;
                    plane_vias_removed.append(entry)?;
                }
            }
        }

        if removed_count > 0 {
            let msg = d6_util::py_format(
                py,
                "ViaValidation: Removed {} dangling vias",
                &[removed_count.into_pyobject(py)?.into_any()],
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
                    empty_string(py)?
                };
                let msg = d6_util::py_format(
                    py,
                    "  Affected nets: {}",
                    &[
                        nets_preview.into_pyobject(py)?.into_any(),
                        // concatenated below (the f-string's + extra part)
                    ],
                )?;
                let combined = msg.add(&extra)?;
                d6_util::py_print(py, &[combined])?;
            }
        }

        if plane_vias_total > 0 {
            let msg = d6_util::py_format(
                py,
                "ViaValidation: Plane vias: {}/{} kept",
                &[
                    plane_vias_kept.into_pyobject(py)?.into_any(),
                    plane_vias_total.into_pyobject(py)?.into_any(),
                ],
            )?;
            d6_util::py_print(py, &[msg])?;
            if plane_vias_removed.len() > 0 {
                d6_util::py_print(py, &["  Removed plane vias (first 5):".into_pyobject(py)?.into_any()])?;
                let first5: Vec<Bound<'_, PyAny>> = plane_vias_removed
                    .try_iter()?
                    .take(5)
                    .collect::<PyResult<Vec<_>>>()?;
                for entry in first5 {
                    let net_obj = entry.get_item(0)?;
                    let pos = entry.get_item(1)?;
                    let layers = entry.get_item(2)?;
                    let conn = entry.get_item(3)?;
                    let msg = d6_util::py_format(
                        py,
                        "    {} at {} layers={} connected={}",
                        &[net_obj.into_any(), pos.into_any(), layers.into_any(), conn.into_any()],
                    )?;
                    d6_util::py_print(py, &[msg])?;
                }
            }
        }

        let frozenset_cls = builtins.getattr("frozenset")?;
        let mut new_state = state;
        new_state.vias = Some(crate::marshal::to_owned::<HashSet<ViaEntry>>(
            &frozenset_cls.call1((&valid_vias,))?,
        )?);
        Ok(new_state)
    }

    /// `_build_trace_endpoint_index`: per-layer sets of endpoint + sampled
    /// mid-trace points (0.5mm step, libm `pow` squares and `** 0.5` close).
    fn build_trace_endpoint_index<'py>(
        &self,
        py: Python<'py>,
        routes: &Bound<'py, PyAny>,
    ) -> PyResult<Bound<'py, PyDict>> {
        let index = PyDict::new(py);
        let builtins = py.import("builtins")?;
        let set_cls = builtins.getattr("set")?;
        let isinstance = builtins.getattr("isinstance")?;
        let trace_cls = py.import("temper_placer.core.board")?.getattr("Trace")?;

        for trace in routes.try_iter()? {
            let trace = trace?;
            let is_trace: bool = isinstance.call1((&trace, &trace_cls))?.extract()?;
            if !is_trace {
                continue;
            }
            let layer = trace.getattr("layer")?;
            let layer_set = if index.contains(&layer)? {
                index.as_any().get_item(&layer)?
            } else {
                let fresh = set_cls.call0()?;
                index.set_item(&layer, &fresh)?;
                fresh
            };
            let start = trace.getattr("start")?;
            let end = trace.getattr("end")?;
            layer_set.call_method1("add", (&start,))?;
            layer_set.call_method1("add", (&end,))?;

            let sx: f64 = start.get_item(0)?.extract()?;
            let sy: f64 = start.get_item(1)?.extract()?;
            let ex: f64 = end.get_item(0)?.extract()?;
            let ey: f64 = end.get_item(1)?.extract()?;
            let length = host_math::pow(
                host_math::pow(ex - sx, 2.0) + host_math::pow(ey - sy, 2.0),
                0.5,
            );
            if length > 0.0 {
                let steps: i64 = (length / 0.5) as i64;
                let steps = steps.max(1);
                for i in 1..steps {
                    let t = (i as f64) / (steps as f64);
                    let x = sx + t * (ex - sx);
                    let y = sy + t * (ey - sy);
                    let pt = PyTuple::new(py, [x.into_pyobject(py)?.into_any(), y.into_pyobject(py)?.into_any()])?;
                    layer_set.call_method1("add", (&pt,))?;
                }
            }
        }
        Ok(index)
    }

    /// `_build_pin_position_index`: netlist pin world positions per layer;
    /// PTH pins register on every STANDARD_LAYER_ORDER layer, SMD on their
    /// layer (default "F.Cu").
    fn build_pin_position_index<'py>(
        &self,
        py: Python<'py>,
        state: &BoardState,
    ) -> PyResult<Bound<'py, PyDict>> {
        let index = PyDict::new(py);
        let netlist = match &state.netlist {
            Some(nl) => nl.bind(py).clone(),
            None => return Ok(index),
        };
        let builtins = py.import("builtins")?;
        let set_cls = builtins.getattr("set")?;
        let pin_geometry = py.import("temper_placer.core.pin_geometry")?;
        let pin_world_position = pin_geometry.getattr("pin_world_position")?;
        let standard_order = py.import("temper_placer.core.board")?.getattr("STANDARD_LAYER_ORDER")?;

        for comp in netlist.getattr("components")?.try_iter()? {
            let comp = comp?;
            for pin in comp.getattr("pins")?.try_iter()? {
                let pin = pin?;
                let pin_pos = pin_world_position.call1((&pin, &comp))?;
                let is_pth: bool = pin.getattr("is_pth")?.extract()?;
                if is_pth {
                    for layer in standard_order.try_iter()? {
                        let layer = layer?;
                        let layer_name = layer.str()?;
                        add_to_layer_set(py, &index, &set_cls, &layer_name, &pin_pos)?;
                    }
                } else {
                    let layer = getattr_default(
                    py,
                    &pin,
                    "layer",
                    crate::grid_hv::str_py(py, DEFAULT_LAYER),
                )?;
                    add_to_layer_set(py, &index, &set_cls, &layer, &pin_pos)?;
                }
            }
        }
        Ok(index)
    }

    /// `_count_connected_layers`: the plane-net predicate + the
    /// temper-drc-rs kernel call.
    fn count_connected_layers<'py>(
        &self,
        py: Python<'py>,
        via: &Bound<'py, PyAny>,
        trace_index: &Bound<'py, PyDict>,
        pin_index: &Bound<'py, PyDict>,
        plane_layer_indices: &Bound<'py, PyAny>,
        drc: &Bound<'py, PyAny>,
    ) -> PyResult<i64> {
        let net = via.getattr("net")?;
        let is_plane_net = if net.is_truthy()? {
            is_plane_net(
                py,
                &net,
                &py.import("temper_placer.core.net_classification")?.into_any(),
            )?
        } else {
            false
        };
        let position = via.getattr("position")?;
        let layers = via.getattr("layers")?;
        let layers_list = py.import("builtins")?.getattr("list")?.call1((&layers,))?;
        let plane_layers = PyList::empty(py);
        for layer in plane_layer_indices.try_iter()? {
            plane_layers.append(layer?.str()?)?;
        }
        let count = drc
            .call_method1(
                "count_connected_layers_py",
                (&position, &layers_list, self.tolerance_mm, trace_index, pin_index, is_plane_net, &plane_layers),
            )?
            .extract::<usize>()?;
        Ok(count as i64)
    }
}

/// The via-dedup stage: `vias` -> `vias` (one via per unique position,
/// first-seen-wins within tolerance).
#[derive(Debug, Clone)]
pub struct ViaDeduplicationStage {
    pub tolerance_mm: f64,
}

#[cfg(feature = "python")]
impl Stage<BoardState> for ViaDeduplicationStage {
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

#[cfg(feature = "python")]
impl ViaDeduplicationStage {
    fn run_inner(&self, py: Python<'_>, state: BoardState) -> PyResult<BoardState> {
        let vias = match &state.vias {
            Some(v) if !v.is_empty() => crate::marshal::to_python::<HashSet<ViaEntry>>(py, v)?.into_bound(py),
            _ => return Ok(state),
        };
        let builtins = py.import("builtins")?;
        // `vias` is a `frozenset`; ITS iteration order is a function of
        // CPython's per-process string hash (`PYTHONHASHSEED`) because
        // `Via.__hash__` mixes `net`/`layers` string fields. Reading it in
        // that order would make "first-seen-wins within tolerance" (this
        // stage's own doc comment) silently process-dependent -- the same
        // determinism defect `TrackDeduplicationStage` has (see that
        // struct's `run_inner` for the full argument). Materialize once and
        // sort by CPython `repr()` -- a pure function of field VALUES, never
        // hash/id -- so the tie-break is reproducible across runs/seeds. The
        // oracle (`_via_validation_run_py_oracle.py`) applies the identical
        // sort so the two arms never diverge on which duplicate survives.
        let vias_list_raw = builtins.getattr("list")?.call1((&vias,))?;
        let mut ordered: Vec<(String, Bound<'_, PyAny>)> = Vec::new();
        for item in vias_list_raw.try_iter()? {
            let item = item?;
            let key: String = item.repr()?.extract()?;
            ordered.push((key, item));
        }
        ordered.sort_by(|a, b| a.0.cmp(&b.0));
        let vias_list = PyList::new(py, ordered.iter().map(|(_, v)| v))?.into_any();
        let positions = PyList::empty(py);
        for via in vias_list.try_iter()? {
            positions.append(via?.getattr("position")?)?;
        }
        let drc = py.import("temper_drc_rs")?;
        let result = drc.call_method1("dedup_via_positions_py", (&positions, self.tolerance_mm))?;
        let kept_indices = result.get_item(0)?;
        let duplicates: usize = result.get_item(1)?.extract()?;

        let unique_vias = PyList::empty(py);
        for i in kept_indices.try_iter()? {
            unique_vias.append(vias_list.get_item(i?)?)?;
        }

        if duplicates > 0 {
            let msg = d6_util::py_format(
                py,
                "ViaDeduplication: Removed {} duplicate vias",
                &[duplicates.into_pyobject(py)?.into_any()],
            )?;
            d6_util::py_print(py, &[msg])?;
        }

        let frozenset_cls = builtins.getattr("frozenset")?;
        let mut new_state = state;
        new_state.vias = Some(crate::marshal::to_owned::<HashSet<ViaEntry>>(
            &frozenset_cls.call1((&unique_vias,))?,
        )?);
        Ok(new_state)
    }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

#[cfg(feature = "python")]
/// `_is_plane_net`: `is_ground_net(net) or is_power_net(net)` through FFI.
fn is_plane_net<'py>(
    _py: Python<'py>,
    net: &Bound<'py, PyAny>,
    net_classify: &Bound<'py, PyAny>,
) -> PyResult<bool> {
    let ground: bool = net_classify
        .call_method1("is_ground_net", (net,))?
        .extract()?;
    let power: bool = net_classify
        .call_method1("is_power_net", (net,))?
        .extract()?;
    Ok(ground || power)
}

#[cfg(feature = "python")]
/// Add `value` into `index[layer_name]` (creating the per-layer set).
fn add_to_layer_set<'py>(
    _py: Python<'py>,
    index: &Bound<'py, PyDict>,
    set_cls: &Bound<'py, PyAny>,
    layer_name: &Bound<'py, PyAny>,
    value: &Bound<'py, PyAny>,
) -> PyResult<()> {
    let layer_set = if index.contains(layer_name)? {
        index.as_any().get_item(layer_name)?
    } else {
        let fresh = set_cls.call0()?;
        index.set_item(layer_name, &fresh)?;
        fresh
    };
    layer_set.call_method1("add", (value,))?;
    Ok(())
}

#[cfg(feature = "python")]
/// An empty CPython string (the no-extra part of the conditional f-string).
fn empty_string<'py>(_py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
    Ok(pyo3::types::PyString::new(_py, "").into_any())
}

#[cfg(feature = "python")]
/// FFI entry for the Python shim: `run_via_validation(state, tolerance_mm,
/// require_both_layers)`.
#[pyfunction]
pub fn run_via_validation(
    py: Python<'_>,
    state: Py<PyAny>,
    tolerance_mm: f64,
    require_both_layers: bool,
) -> PyResult<Py<PyAny>> {
    let rust_state = crate::d1_bridge::from_python(py, state.bind(py)).map_err(|e| {
        pyo3::exceptions::PyRuntimeError::new_err(format!("{STAGE_NAME}: {e}"))
    })?;
    let stage = ViaValidationStage {
        tolerance_mm,
        require_both_layers,
    };
    let out = stage.run(rust_state).map_err(|e| crate::config_attach_stage::to_pyerr(&e))?;
    crate::d1_bridge::to_python(py, state.bind(py), &out, &["vias"])
}

#[cfg(feature = "python")]
/// FFI entry for the Python shim: `run_via_deduplication(state,
/// tolerance_mm)`.
#[pyfunction]
pub fn run_via_deduplication(
    py: Python<'_>,
    state: Py<PyAny>,
    tolerance_mm: f64,
) -> PyResult<Py<PyAny>> {
    let rust_state = crate::d1_bridge::from_python(py, state.bind(py)).map_err(|e| {
        pyo3::exceptions::PyRuntimeError::new_err(format!("{STAGE_NAME_DEDUP}: {e}"))
    })?;
    let stage = ViaDeduplicationStage { tolerance_mm };
    let out = stage.run(rust_state).map_err(|e| crate::config_attach_stage::to_pyerr(&e))?;
    crate::d1_bridge::to_python(py, state.bind(py), &out, &["vias"])
}
