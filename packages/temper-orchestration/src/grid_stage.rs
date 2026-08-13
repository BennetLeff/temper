// The D3 `ClearanceGridStage` of the Rust Orchestration Engine plan
// (2026-08-09-001, Phase D batch D3): a `Stage<BoardState>` implementor
// mirroring `deterministic/stages/_grid_stage.py`.
//
// The run() orchestration moves to Rust: the pad-collection loop (net ->
// pads mapping, per-pad geometry via `pin_world_position` + `pad_sizes`),
// the per-net blocking pass (net-class-aware clearance with inner-layer
// capping), the pre-route HV creepage-expansion pass (HV-pad set resolution
// via `_grid_hv.hv_pad_set`, per-layer `effective_creepage`, rect/circle
// Minkowski expansion, `_EXPANSION_LOG` append), the fence invocation
// (`_grid_fence.check_clearance_grid_conservatism` called through the
// PYTHON module at runtime -- the monkey-patchable seam the U3 tests rely
// on -- raising `FenceViolation` on a miss), and the EXP-13 exclusion-zone
// blocking (the bbox computation here + the per-cell `-2` write via the
// temper-geometry `block_exclusion_zone_into_grid_py` kernel). The leaf
// objects
// stay Python: the `ClearanceGrid` data type (`_grid_core.py` -- its
// cell-rasterisation compute is already in temper-geometry grid_raster.rs,
// and its `blocked_count`/`is_available` leaf reductions are now in
// temper-geometry grid_leaf.rs),
// the `_grid_hv`/`_grid_fence` helpers and exceptions, and the module-level
// `_EXPANSION_LOG`.
//
// Bit-exactness notes:
// - `int(round(rotation)) % 180` calls CPython's `round` (banker's
//   rounding) on the ORIGINAL rotation object, not Rust `f64::round`
//   (half-away-from-zero -- diverges on .5 boundaries).
// - `max(size.X, size.Y)` is CPython `max` (first-arg-wins on NaN), not
//   `f64::max`.
// - The fence/perf-budget helpers are called through their Python modules
//   so the established monkey-patch tests keep working; the shims delegate
//   to the Rust kernels in grid_fence.rs.

#[cfg(feature = "python")]
use std::borrow::Cow;

#[cfg(feature = "python")]
use pyo3::prelude::*;
#[cfg(feature = "python")]
use pyo3::types::{PyDict, PyList, PyTuple};

#[cfg(feature = "python")]
use crate::board_state::BoardState;
#[cfg(feature = "python")]
use crate::derivation_stage::pyerr_stage;
#[cfg(feature = "python")]
use crate::grid_hv::{getattr_default, py_float, str_of};
#[cfg(feature = "python")]
use crate::stage::{Stage, StageError};
#[cfg(feature = "python")]
use temper_data_model::{PlacementSet};

#[cfg(feature = "python")]
/// The clearance-grid stage: board + netlist -> `BoardState.grid`.
#[derive(Debug, Clone)]
pub struct ClearanceGridStage {
    pub cell_size_mm: f64,
    pub layer_count: i64,
    pub pad_sizes: Option<Py<PyAny>>,
    pub max_clearance_mm: f64,
    pub net_class_clearances: Option<Py<PyAny>>,
    pub net_classes: Option<Py<PyAny>>,
    pub pth_mask_expansion_mm: f64,
    pub smd_mask_expansion_mm: f64,
    pub inner_layer_clearance_mm: f64,
    pub hv_exclusion_zones: Option<Py<PyAny>>,
    pub default_trace_width_mm: f64,
}

#[cfg(feature = "python")]
impl Stage<BoardState> for ClearanceGridStage {
    fn name(&self) -> Cow<'static, str> {
        Cow::Borrowed("clearance_grid")
    }

    fn run(&self, state: BoardState) -> Result<BoardState, StageError> {
        self.run_guarded(state).map_err(|e| pyerr_stage("clearance_grid", e))
    }
}

#[cfg(feature = "python")]
impl ClearanceGridStage {
    /// Panic-guarded `run_inner`: a Rust panic is converted to a Python
    /// RuntimeError rather than unwinding through the pyo3 frame (the plan's
    /// error model, `stage_guard` in derivation_stage.rs). The inner result
    /// carries the ORIGINAL Python `PyErr` so Python-exception paths
    /// (``FenceViolation``, ``ConfigError``) propagate by TYPE through the
    /// FFI wrapper, exactly like the oracle's raise.
    fn run_guarded(&self, state: BoardState) -> Result<BoardState, PyErr> {
        match std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| self.run_inner(state))) {
            Ok(result) => result,
            Err(_) => Err(pyo3::exceptions::PyRuntimeError::new_err(
                "clearance_grid: stage panicked",
            )),
        }
    }

    fn run_inner(&self, state: BoardState) -> Result<BoardState, PyErr> {
        Python::attach(|py| {
            // `if not state.board: return state` -- truthiness guard.
            let board = match &state.board {
                Some(b) if b.bind(py).is_truthy()? => b.clone_ref(py),
                _ => return Ok(state),
            };
            let board_width = board.bind(py).getattr("width")?;
            let board_height = board.bind(py).getattr("height")?;
            let grid_cls = py
                .import("temper_placer.deterministic.stages._grid_core")?
                .getattr("ClearanceGrid")?;
            let grid = grid_cls
                .call1((board_width, board_height, self.cell_size_mm, self.layer_count))?;

            let pad_sizes = empty_or(py, &self.pad_sizes, || PyDict::new(py).into_any());
            let net_class_clearances =
                empty_or(py, &self.net_class_clearances, || PyDict::new(py).into_any());
            let net_classes = empty_or(py, &self.net_classes, || PyDict::new(py).into_any());
            let hv_zones = empty_or(py, &self.hv_exclusion_zones, || PyList::empty(py).into_any());

            // `if state.netlist:` -- truthiness of the (pyclass) Netlist.
            if let Some(nl) = &state.netlist
                && nl.bind(py).is_truthy()?
            {
                let placements_dict = placements_dict(py, &state)?;
                let all_pads = block_pads(
                    py,
                    &grid,
                    nl,
                    &placements_dict,
                    &pad_sizes,
                    &net_class_clearances,
                    &net_classes,
                    self,
                )?;
                hv_expansion(
                    py,
                    &grid,
                    nl,
                    &placements_dict,
                    &pad_sizes,
                    &hv_zones,
                    &all_pads,
                    self,
                )?;
            }

            // The U3 fence: runs only when the expansion log is non-empty.
            let expansion_log = py
                .import("temper_placer.deterministic.stages._grid_fence")?
                .getattr("_EXPANSION_LOG")?;
            if expansion_log.len()? > 0 {
                run_fence(py, &grid, &expansion_log)?;
            }

            // EXP-13 exclusion zones -- blocked for the excluded nets on
            // every layer (outside the netlist guard, exactly like the
            // oracle).
            exclusion_zones(py, &grid, hv_zones.bind(py))?;

            let mut new_state = state;
            new_state.grid = Some(grid.unbind());
            Ok(new_state)
        })
    }
}

#[cfg(feature = "python")]
/// FFI entry for the Python shim: `run_clearance_grid_stage(...)`.
#[pyfunction]
#[allow(clippy::too_many_arguments)]
#[pyo3(signature = (state, cell_size_mm, layer_count, pad_sizes, max_clearance_mm, net_class_clearances, net_classes, pth_mask_expansion_mm, smd_mask_expansion_mm, inner_layer_clearance_mm, hv_exclusion_zones, default_trace_width_mm))]
pub fn run_clearance_grid_stage(
    py: Python<'_>,
    state: Py<PyAny>,
    cell_size_mm: f64,
    layer_count: i64,
    pad_sizes: Py<PyAny>,
    max_clearance_mm: f64,
    net_class_clearances: Py<PyAny>,
    net_classes: Py<PyAny>,
    pth_mask_expansion_mm: f64,
    smd_mask_expansion_mm: f64,
    inner_layer_clearance_mm: f64,
    hv_exclusion_zones: Py<PyAny>,
    default_trace_width_mm: f64,
) -> PyResult<Py<PyAny>> {
    let rust_state = crate::d1_bridge::from_python(py, state.bind(py)).map_err(|e| {
        pyo3::exceptions::PyRuntimeError::new_err(format!("clearance_grid: {e}"))
    })?;
    let stage = ClearanceGridStage {
        cell_size_mm,
        layer_count,
        pad_sizes: Some(pad_sizes),
        max_clearance_mm,
        net_class_clearances: Some(net_class_clearances),
        net_classes: Some(net_classes),
        pth_mask_expansion_mm,
        smd_mask_expansion_mm,
        inner_layer_clearance_mm,
        hv_exclusion_zones: Some(hv_exclusion_zones),
        default_trace_width_mm,
    };
    let out = stage.run_guarded(rust_state)?;
    crate::d1_bridge::to_python(py, state.bind(py), &out, &["grid"])
}

#[cfg(feature = "python")]
fn empty_or<'py>(
    py: Python<'py>,
    opt: &Option<Py<PyAny>>,
    empty: impl FnOnce() -> Bound<'py, PyAny>,
) -> Py<PyAny> {
    match opt {
        Some(v) => v.clone_ref(py),
        None => empty().into_any().unbind(),
    }
}

#[cfg(feature = "python")]
/// `dict(state.placements) if state.placements else {}` -- the placements
/// lookup dict (an EMPTY dict, not None, on the falsy branch).
fn placements_dict(py: Python<'_>, state: &BoardState) -> PyResult<Py<PyAny>> {
    match &state.placements {
        Some(p) if !p.is_empty() => {
            // U6 (O-C3) group-2: the owned `PlacementSet` is rebuilt into the
            // Python frozenset, then `dict(...)`-ed exactly like the oracle.
            let fs = crate::marshal::to_python::<PlacementSet>(py, p)?;
            Ok(py
                .import("builtins")?
                .getattr("dict")?
                .call1((fs,))?
                .into_any()
                .unbind())
        }
        _ => Ok(PyDict::new(py).into_any().unbind()),
    }
}

// ---------------------------------------------------------------------------
// Pad collection + per-net blocking
// ---------------------------------------------------------------------------

#[cfg(feature = "python")]
/// The `if state.netlist:` blocking block: build `net_pads` (net name ->
/// list of pad dicts) and the `all_pads_for_expansion` list, then block
/// every pad with its net-class-aware per-layer clearance. Returns the pad
/// list for the HV expansion pass (the oracle keeps the same list alive).
#[allow(clippy::too_many_arguments)]
fn block_pads<'py>(
    py: Python<'py>,
    grid: &Bound<'py, PyAny>,
    netlist: &Py<PyAny>,
    placements_dict: &Py<PyAny>,
    pad_sizes: &Py<PyAny>,
    net_class_clearances: &Py<PyAny>,
    net_classes: &Py<PyAny>,
    stage: &ClearanceGridStage,
) -> PyResult<Py<PyAny>> {
    let pin_world_position = py
        .import("temper_placer.core.pin_geometry")?
        .getattr("pin_world_position")?;
    let net_pads = PyDict::new(py);
    let all_pads_for_expansion = PyList::empty(py);

    for component in netlist.bind(py).getattr("components")?.try_iter()? {
        let component = component?;
        // pos = placements_dict.get(component.ref, component.initial_position)
        let pos = placements_dict
            .bind(py)
            .getattr("get")?
            .call1((component.getattr("ref")?, component.getattr("initial_position")?))?;
        if pos.is_none() {
            continue;
        }
        let comp_ref = component.getattr("ref")?;
        for pin in component.getattr("pins")?.try_iter()? {
            let pin = pin?;
            let pin_pos = pin_world_position.call1((&pin, &component))?;
            let pin_name = pin.getattr("name")?;

            let pad_key = PyTuple::new(py, [comp_ref.clone(), pin_name.clone()])?;
            let real_pad = dict_get(py, pad_sizes, &pad_key)?;
            let (pad_radius, pad_width, pad_height) = match &real_pad {
                Some(p) => {
                    let size = p.getattr("size")?;
                    let sx: f64 = size.getattr("X")?.extract()?;
                    let sy: f64 = size.getattr("Y")?.extract()?;
                    (py_max(sx, sy) / 2.0, sx, sy)
                }
                None => (0.5, 1.0, 1.0),
            };

            // net = pin.net or ""
            let net: String = {
                let v = pin.getattr("net")?;
                if v.is_none() {
                    String::new()
                } else {
                    v.extract()?
                }
            };

            // if net not in net_pads: net_pads[net] = []
            let net_list: Py<PyAny> = match net_pads.get_item(&net)? {
                Some(l) => l.unbind(),
                None => {
                    let l = PyList::empty(py);
                    net_pads.set_item(&net, &l)?;
                    l.into_any().unbind()
                }
            };

            let target_layers = target_layers(py, &pin, stage.layer_count)?;

            let pad_dict = PyDict::new(py);
            pad_dict.set_item("pos", &pin_pos)?;
            pad_dict.set_item("size", PyTuple::new(py, [pad_width, pad_height])?)?;
            pad_dict.set_item("radius", pad_radius)?;
            pad_dict.set_item("shape", pin.getattr("shape")?)?;
            pad_dict.set_item(
                "rotation",
                getattr_default(py, &pin, "rotation", py_float(py, 0.0))?,
            )?;
            pad_dict.set_item("layers", &target_layers)?;
            pad_dict.set_item("is_pth", pin.getattr("is_pth")?)?;
            pad_dict.set_item("ref", &comp_ref)?;
            pad_dict.set_item("name", &pin_name)?;
            net_list.bind(py).call_method1("append", (&pad_dict,))?;
            all_pads_for_expansion.append(&pad_dict)?;
        }
    }

    // Block all pads with clearance based on the pad's net class.
    for (net_name_obj, pads) in dict_items(py, &net_pads)? {
        let net_name: String = net_name_obj.bind(py).extract()?;
        for pad in pads.bind(py).try_iter()? {
            let pad = pad?;
            let is_pth: bool = pad.get_item("is_pth")?.extract()?;
            let mask_expansion = if is_pth {
                stage.pth_mask_expansion_mm
            } else {
                stage.smd_mask_expansion_mm
            };

            let pad_key = PyTuple::new(py, [pad.get_item("ref")?, pad.get_item("name")?])?;
            let real_pad = dict_get(py, pad_sizes, &pad_key)?;

            let mut use_rect_blocking = false;
            let mut rect_size = (0.0, 0.0);
            if let Some(rp) = &real_pad {
                let shape: String = rp.getattr("shape")?.extract()?;
                if ["rect", "roundrect", "oval"].contains(&shape.as_str()) {
                    let norm_rot = py_round_mod180(py, rp)?;
                    let sx: f64 = rp.getattr("size")?.getattr("X")?.extract()?;
                    let sy: f64 = rp.getattr("size")?.getattr("Y")?.extract()?;
                    if norm_rot == 0 {
                        rect_size = (sx, sy);
                        use_rect_blocking = true;
                    } else if norm_rot == 90 {
                        rect_size = (sy, sx);
                        use_rect_blocking = true;
                    }
                }
            }
            // `if not use_rect_blocking and pad.get("shape") in [...]: pass`
            // is a deliberate no-op in the oracle; not reproduced.

            for layer_obj in pad.get_item("layers")?.try_iter()? {
                let layer_idx: i64 = layer_obj?.extract()?;
                if layer_idx < stage.layer_count {
                    let net_clearance = get_clearance_for_net(
                        py,
                        &net_name,
                        layer_idx,
                        net_classes,
                        Some(netlist),
                        net_class_clearances,
                        stage,
                    )?;
                    // EXP-24: mechanical pads (no net) use zero clearance.
                    let current_mask = if net_name.is_empty() {
                        0.0
                    } else {
                        mask_expansion
                    };
                    let current_clearance = if net_name.is_empty() {
                        0.0
                    } else {
                        net_clearance
                    };
                    let total_clearance = current_clearance
                        + current_mask
                        + (stage.default_trace_width_mm / 2.0);

                    if use_rect_blocking {
                        grid.call_method1(
                            "block_rect",
                            (
                                pad.get_item("pos")?,
                                PyTuple::new(py, [rect_size.0, rect_size.1])?,
                                total_clearance,
                                layer_idx,
                                &net_name,
                                false,
                            ),
                        )?;
                    } else {
                        grid.call_method1(
                            "block_circle",
                            (
                                pad.get_item("pos")?,
                                pad.get_item("radius")?,
                                total_clearance,
                                layer_idx,
                                &net_name,
                            ),
                        )?;
                    }
                }
            }
        }
    }
    Ok(all_pads_for_expansion.into_any().unbind())
}

// ---------------------------------------------------------------------------
// HV creepage expansion pass
// ---------------------------------------------------------------------------

#[cfg(feature = "python")]
/// The pre-route creepage expansion: resolve the HV pad set, then re-block
/// each HV pad with its per-layer effective creepage distance, appending an
/// entry to `_grid_fence._EXPANSION_LOG`.
#[allow(clippy::too_many_arguments)]
fn hv_expansion<'py>(
    py: Python<'py>,
    grid: &Bound<'py, PyAny>,
    netlist: &Py<PyAny>,
    placements_dict: &Py<PyAny>,
    pad_sizes: &Py<PyAny>,
    hv_zones: &Py<PyAny>,
    all_pads_for_expansion: &Py<PyAny>,
    stage: &ClearanceGridStage,
) -> PyResult<()> {
    let grid_hv = py.import("temper_placer.deterministic.stages._grid_hv")?;
    let grid_fence = py.import("temper_placer.deterministic.stages._grid_fence")?;

    // component_positions = {ref: positions ... if positions is not None}
    let component_positions = PyDict::new(py);
    for component in netlist.bind(py).getattr("components")?.try_iter()? {
        let component = component?;
        let pos = placements_dict
            .bind(py)
            .getattr("get")?
            .call1((component.getattr("ref")?, component.getattr("initial_position")?))?;
        if !pos.is_none() {
            component_positions.set_item(component.getattr("ref")?, &pos)?;
        }
    }

    let hv_pads = grid_hv
        .getattr("hv_pad_set")?
        .call1((all_pads_for_expansion, hv_zones, component_positions))?;

    let expansion_log = grid_fence.getattr("_EXPANSION_LOG")?;
    expansion_log.call_method0("clear")?;

    // The blocked-cell reduction (`blocked_count_on_layer`) is a
    // temper-geometry kernel (`grid_leaf.rs`); fetch the per-layer arrays
    // and the kernel once rather than round-tripping through the Python
    // method per (pad, layer).
    let count_kernel = py.import("temper_geometry")?.getattr("count_blocked_cells_py")?;
    let trace_arrays = grid.getattr("_trace_net_ids")?;
    let pad_arrays = grid.getattr("_pad_net_ids")?;

    for pad in all_pads_for_expansion.bind(py).try_iter()? {
        let pad = pad?;
        let pad_ref = pad.get_item("ref")?;
        let pad_name = pad.get_item("name")?;
        // if (pad["ref"], pad["name"]) not in hv_pads: continue
        let key = PyTuple::new(py, [pad_ref.clone(), pad_name.clone()])?;
        let in_hv: bool = hv_pads.call_method1("__contains__", (key,))?.extract()?;
        if !in_hv {
            continue;
        }

        for layer_obj in pad.get_item("layers")?.try_iter()? {
            let layer_idx: i64 = layer_obj?.extract()?;
            if layer_idx >= stage.layer_count {
                continue;
            }
            let layer_name = grid_hv
                .getattr("_layer_index_to_name")?
                .call1((layer_idx, stage.layer_count))?;
            let eff_creep = grid_hv
                .getattr("effective_creepage")?
                .call1((layer_name, 6.0))?; // allow-safety-constant: HV clearance default

            let pre_count: i64 = count_kernel
                .call1((trace_arrays.get_item(layer_idx)?, pad_arrays.get_item(layer_idx)?))?
                .extract()?;

            let pad_key = PyTuple::new(py, [pad_ref.clone(), pad_name.clone()])?;
            let real_pad = dict_get(py, pad_sizes, &pad_key)?;

            let mut use_rect = false;
            let mut rect_size = (0.0, 0.0);
            if let Some(rp) = &real_pad {
                let shape: String = rp.getattr("shape")?.extract()?;
                if ["rect", "roundrect", "oval"].contains(&shape.as_str()) {
                    let rot = py_round_mod180(py, rp)?;
                    let sx: f64 = rp.getattr("size")?.getattr("X")?.extract()?;
                    let sy: f64 = rp.getattr("size")?.getattr("Y")?.extract()?;
                    if rot == 0 {
                        rect_size = (sx, sy);
                        use_rect = true;
                    } else if rot == 90 {
                        rect_size = (sy, sx);
                        use_rect = true;
                    }
                }
            }
            let eff: f64 = eff_creep.extract()?;
            if use_rect {
                let (w, h) = rect_size;
                grid.call_method1(
                    "block_rect",
                    (
                        pad.get_item("pos")?,
                        PyTuple::new(py, [w + 2.0 * eff, h + 2.0 * eff])?,
                        0.0,
                        layer_idx,
                        py.None(),
                        true,
                    ),
                )?;
            } else {
                let radius: f64 = pad.get_item("radius")?.extract()?;
                grid.call_method1(
                    "block_circle",
                    (
                        pad.get_item("pos")?,
                        radius + eff,
                        0.0,
                        layer_idx,
                        py.None(),
                        false,
                    ),
                )?;
            }

            let size_xy: Bound<'py, PyAny> = match &real_pad {
                Some(rp) => PyTuple::new(
                    py,
                    [
                        rp.getattr("size")?.getattr("X")?,
                        rp.getattr("size")?.getattr("Y")?,
                    ],
                )?
                .into_any(),
                None => PyTuple::new(py, [0.0, 0.0])?.into_any(),
            };
            let post_count: i64 = count_kernel
                .call1((trace_arrays.get_item(layer_idx)?, pad_arrays.get_item(layer_idx)?))?
                .extract()?;
            let entry = PyTuple::new(
                py,
                [
                    pad_ref.clone().unbind(),
                    pad_name.clone().unbind(),
                    py_int(py, layer_idx),
                    pad.get_item("pos")?.unbind(),
                    pad.get_item("shape")?.unbind(),
                    pad.get_item("radius")?.unbind(),
                    size_xy.unbind(),
                    eff_creep.unbind(),
                    py_int(py, post_count - pre_count),
                ],
            )?;
            expansion_log.call_method1("append", (entry,))?;
        }
    }
    Ok(())
}

// ---------------------------------------------------------------------------
// Fence + exclusion zones
// ---------------------------------------------------------------------------

#[cfg(feature = "python")]
/// The U3 fence block: call `_grid_fence.check_clearance_grid_conservatism`
/// through the PYTHON module (the monkey-patch seam), raise `FenceViolation`
/// on a miss, then the soft perf-budget warning.
fn run_fence(
    py: Python<'_>,
    grid: &Bound<'_, PyAny>,
    expansion_log: &Bound<'_, PyAny>,
) -> PyResult<()> {
    let grid_fence = py.import("temper_placer.deterministic.stages._grid_fence")?;
    let t0 = std::time::Instant::now();
    let check_fn = grid_fence.getattr("check_clearance_grid_conservatism")?;
    let violations = check_fn.call1((grid, expansion_log))?;
    let fence_elapsed_ms = t0.elapsed().as_secs_f64() * 1000.0;

    if violations.len()? > 0 {
        let first = violations.get_item(0)?;
        let reason: String = first.get_item("reason")?.extract()?;
        let n = violations.len()?;
        let msg = format!(
            "U3 fence failed on expansion: {} (additional violations: {})",
            reason,
            n - 1
        );
        let exc = grid_fence.getattr("FenceViolation")?.call1((msg,))?;
        return Err(PyErr::from_value(exc));
    }

    // Soft perf-budget warning (R4); the oracle approximates stage elapsed
    // by the fence's own wall-time on its first run.
    let stage_elapsed_ms = fence_elapsed_ms.max(1.0);
    let budget_fn = grid_fence.getattr("check_clearance_grid_perf_budget")?;
    let (over_budget, warning): (bool, Option<String>) = budget_fn
        .call1((fence_elapsed_ms, stage_elapsed_ms))?
        .extract()?;
    if over_budget && let Some(w) = warning {
        let line = format!("  [clearance_grid fence] {w}");
        py.import("builtins")?.getattr("print")?.call1((line,))?;
    }
    Ok(())
}

#[cfg(feature = "python")]
/// EXP-13: block each excluded net's zone on all layers with direct numpy
/// writes (`arr[row, col] = -2`, preserving the oracle's per-cell guard and
/// its lack of cache invalidation).
fn exclusion_zones(
    py: Python<'_>,
    grid: &Bound<'_, PyAny>,
    hv_zones: &Bound<'_, PyAny>,
) -> PyResult<()> {
    let n_zones = hv_zones.len()?;
    if n_zones == 0 {
        return Ok(());
    }
    py.import("builtins")?
        .getattr("print")?
        .call1((format!("  HV exclusion zones: {n_zones}"),))?;

    for hvz in hv_zones.try_iter()? {
        let hvz = hvz?;
        let excluded_nets = hvz.getattr("excluded_nets")?;
        for excluded_net in excluded_nets.try_iter()? {
            let excluded_net = excluded_net?;
            let net_id: i64 = grid
                .call_method1("get_net_id", (&excluded_net,))?
                .extract()?;
            let center = hvz.getattr("center")?;
            let cx: f64 = center.get_item(0)?.extract()?;
            let cy: f64 = center.get_item(1)?.extract()?;
            let size = hvz.getattr("size")?;
            let half_w: f64 = size.get_item(0)?.extract::<f64>()? / 2.0;
            let half_h: f64 = size.get_item(1)?.extract::<f64>()? / 2.0;
            let cell: f64 = grid.getattr("cell_size_mm")?.extract()?;
            let cols: i64 = grid.getattr("cols")?.extract()?;
            let rows: i64 = grid.getattr("rows")?.extract()?;

            let min_col = (0i64).max(((cx - half_w) / cell) as i64);
            let max_col = cols.min(((cx + half_w) / cell) as i64 + 1);
            let min_row = (0i64).max(((cy - half_h) / cell) as i64);
            let max_row = rows.min(((cy + half_h) / cell) as i64 + 1);

            // The per-cell -2 write loop is a temper-geometry kernel
            // (`grid_leaf.rs::block_exclusion_zone`); the bbox computation
            // above stays here (it is the same O(1) orchestration the
            // rasterisation kernels already leave in Python).
            let block_zone_kernel = py
                .import("temper_geometry")?
                .getattr("block_exclusion_zone_into_grid_py")?;
            let trace_arrays = grid.getattr("_trace_net_ids")?;
            for layer_idx in 0..(grid.getattr("layer_count")?.extract::<i64>()?) {
                let target_grid = trace_arrays.get_item(layer_idx)?;
                block_zone_kernel.call1((
                    &target_grid,
                    net_id as i32,
                    min_row as usize,
                    max_row as usize,
                    min_col as usize,
                    max_col as usize,
                ))?;
            }
        }
        // print(f"    {hvz.name}: blocking {hvz.excluded_nets} in ...")
        let name = str_of(&hvz.getattr("name")?)?;
        let excluded_nets_s = str_of(&excluded_nets)?;
        let size = hvz.getattr("size")?;
        let size0 = str_of(&size.get_item(0)?)?;
        let size1 = str_of(&size.get_item(1)?)?;
        let center_s = str_of(&hvz.getattr("center")?)?;
        py.import("builtins")?.getattr("print")?.call1((
            format!("    {name}: blocking {excluded_nets_s} in {size0}x{size1}mm zone at {center_s}"),
        ))?;
    }
    Ok(())
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

#[cfg(feature = "python")]
/// `dict.get(key)` -> the value or `None`.
fn dict_get<'py>(
    py: Python<'py>,
    dict: &Py<PyAny>,
    key: &Bound<'py, PyAny>,
) -> PyResult<Option<Bound<'py, PyAny>>> {
    let v = dict.bind(py).call_method1("get", (key,))?;
    if v.is_none() {
        Ok(None)
    } else {
        Ok(Some(v))
    }
}

#[cfg(feature = "python")]
/// `int(round(rotation)) % 180` -- CPython's `round` (banker's rounding),
/// applied to the ORIGINAL rotation object, then truncated and reduced.
fn py_round_mod180(py: Python<'_>, obj: &Bound<'_, PyAny>) -> PyResult<i64> {
    let rot = getattr_default(py, obj, "rotation", py_float(py, 0.0))?;
    let rounded = py.import("builtins")?.getattr("round")?.call1((rot,))?;
    Ok(rounded.extract::<i64>()? % 180)
}

/// CPython `max(a, b)`: first argument on ties and NaN, never `f64::max`.
fn py_max(a: f64, b: f64) -> f64 {
    if b > a {
        b
    } else {
        a
    }
}

#[cfg(feature = "python")]
fn py_int(py: Python<'_>, v: i64) -> Py<PyAny> {
    v.into_pyobject(py)
        .map(|b| b.into_any().unbind())
        .unwrap_or_else(|_| py.None())
}

#[cfg(feature = "python")]
/// The oracle's `target_layers` selection from a pin.
fn target_layers<'py>(
    py: Python<'py>,
    pin: &Bound<'py, PyAny>,
    layer_count: i64,
) -> PyResult<Bound<'py, PyList>> {
    let is_pth: bool = pin.getattr("is_pth")?.extract()?;
    let layer = pin.getattr("layer")?;
    let layer_str: String = if layer.is_none() {
        String::new()
    } else {
        layer.extract()?
    };
    let list = PyList::empty(py);
    if is_pth || layer_str == "all" {
        for i in 0..layer_count {
            list.append(i)?;
        }
    } else if layer_str == "F.Cu" {
        list.append(0)?;
    } else if layer_str == "B.Cu" {
        list.append(layer_count - 1)?;
    } else if layer_str == "In1.Cu" && layer_count > 1 {
        list.append(1)?;
    } else if layer_str == "In2.Cu" && layer_count > 2 {
        list.append(2)?;
    } else {
        for i in 0..layer_count {
            list.append(i)?;
        }
    }
    Ok(list)
}

#[cfg(feature = "python")]
/// `dict.items()` in insertion order.
fn dict_items(
    py: Python<'_>,
    dict: &Bound<'_, PyAny>,
) -> PyResult<Vec<(Py<PyAny>, Py<PyAny>)>> {
    let mut out = Vec::new();
    let items = dict.call_method0("items")?;
    for item in items.try_iter()? {
        let item = item?;
        out.push((item.get_item(0)?.unbind(), item.get_item(1)?.unbind()));
    }
    let _ = py;
    Ok(out)
}

#[cfg(feature = "python")]
/// The net-class-aware per-layer clearance lookup (with the inner-layer cap).
#[allow(clippy::too_many_arguments)]
fn get_clearance_for_net<'py>(
    py: Python<'py>,
    net_name: &str,
    layer: i64,
    net_classes: &Py<PyAny>,
    netlist: Option<&Py<PyAny>>,
    net_class_clearances: &Py<PyAny>,
    stage: &ClearanceGridStage,
) -> PyResult<f64> {
    if net_name.is_empty() {
        return Ok(stage.max_clearance_mm);
    }
    // net_class = self.net_classes.get(net_name)
    let mut net_class: Option<String> = net_classes
        .bind(py)
        .call_method1("get", (net_name,))?
        .extract()?;
    // Fall back to netlist if not in config.
    if net_class.as_deref().map(str::is_empty).unwrap_or(true)
        && let Some(nl) = netlist
    {
        for net in nl.bind(py).getattr("nets")?.try_iter()? {
            let net = net?;
            let name: String = net.getattr("name")?.extract()?;
            if name == net_name {
                net_class = getattr_default(py, &net, "net_class", py.None())?.extract()?;
                break;
            }
        }
    }
    let clearance: f64 = match net_class {
        Some(nc) if !nc.is_empty() => {
            if net_class_clearances.bind(py).contains(&nc)? {
                net_class_clearances.bind(py).get_item(&nc)?.extract()?
            } else {
                net_class_clearances
                    .bind(py)
                    .call_method1("get", ("Signal", 0.2))?
                    .extract()?
            }
        }
        _ => net_class_clearances
            .bind(py)
            .call_method1("get", ("Signal", 0.2))?
            .extract()?,
    };
    // Cap clearance on inner layers (creepage only applies to surface layers).
    let is_inner_layer = 0 < layer && layer < stage.layer_count - 1;
    if is_inner_layer && clearance > stage.inner_layer_clearance_mm {
        return Ok(stage.inner_layer_clearance_mm);
    }
    Ok(clearance)
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

    // -- py_max ------------------------------------------------------------

    /// CPython `max(NaN, x)` returns NaN; `max(x, NaN)` returns x.
    /// Replicate exactly: first arg wins on NaN.
    #[cfg_attr(test, test)]
    fn py_max_nan_first_argument_wins() {
        assert!(py_max(f64::NAN, 1.0).is_nan());
        assert_eq!(py_max(1.0, f64::NAN), 1.0);
        assert!(py_max(f64::NAN, f64::NAN).is_nan());
    }

    /// CPython `max` keeps the first argument on tie, including -0.0 vs +0.0.
    #[cfg_attr(test, test)]
    fn py_max_ties_keep_first() {
        assert_eq!(py_max(0.0, -0.0), 0.0);
        // -0.0 is the first argument -> returned
        let r = py_max(-0.0, 0.0);
        assert!(r == -0.0 && r.is_sign_negative(),
            "py_max(-0.0, 0.0) must return -0.0, got {r}");
        assert_eq!(py_max(3.0, 3.0), 3.0);
        assert_eq!(py_max(-0.0, -0.0).to_bits(), (-0.0f64).to_bits());
    }

    /// CPython `max` on infinity works like the conventional max.
    #[cfg_attr(test, test)]
    fn py_max_infinity() {
        assert_eq!(py_max(f64::INFINITY, 0.0), f64::INFINITY);
        assert_eq!(py_max(0.0, f64::INFINITY), f64::INFINITY);
        assert_eq!(py_max(f64::NEG_INFINITY, 0.0), 0.0);
        assert_eq!(py_max(0.0, f64::NEG_INFINITY), 0.0);
        // CPython max(-inf, NaN) -> -inf (first arg wins when second is NaN)
        assert_eq!(py_max(f64::NEG_INFINITY, f64::NAN), f64::NEG_INFINITY);
        // CPython max(NaN, -inf) -> NaN (first arg is NaN)
        assert!(py_max(f64::NAN, f64::NEG_INFINITY).is_nan());
    }

    /// `is_inner_layer` helper (inline in get_clearance_for_net).
    fn is_inner_layer(layer: i64, layer_count: i64) -> bool {
        0 < layer && layer < layer_count - 1
    }

    #[cfg_attr(test, test)]
    fn inner_layer_logic() {
        // 2-layer: no inner
        assert!(!is_inner_layer(0, 2));
        assert!(!is_inner_layer(1, 2));
        // 4-layer: layers 1 and 2 are inner
        assert!(!is_inner_layer(0, 4));
        assert!(is_inner_layer(1, 4));
        assert!(is_inner_layer(2, 4));
        assert!(!is_inner_layer(3, 4));
        // degenerate
        assert!(!is_inner_layer(0, 1));
        assert!(!is_inner_layer(0, 0));
        assert!(!is_inner_layer(1, 0));
    }

    // -----------------------------------------------------------------------
    // Deterministic mirrors of `proptests`' three properties (P1-P3) below --
    // `proptest` is a dev-dependency (the `proptest-dev-dependency` exclusion
    // class), so its macro bodies cannot be registered directly; each
    // property here reproduces the SAME assertion over a fixed, seeded
    // `SplitMix64` corpus. The native, randomized proptest module is
    // UNCHANGED and keeps exploring randomly.
    use crate::wasm_campaign_prng::SplitMix64;

    fn campaign_normal_f64(rng: &mut SplitMix64) -> f64 {
        rng.range(-1e6, 1e6)
    }

    /// P1: py_max returns the conventional maximum for non-NaN f64 values.
    fn p1_py_max_returns_larger_impl(seed: u64) {
        let mut rng = SplitMix64::new(seed);
        let a = campaign_normal_f64(&mut rng);
        let b = campaign_normal_f64(&mut rng);
        let r = py_max(a, b);
        assert!(r >= a && r >= b, "py_max({a},{b})={r} not >= both (seed={seed})");
    }

    /// P2: py_max returns one of its arguments (bit-identical).
    fn p2_py_max_returns_one_of_inputs_impl(seed: u64) {
        let mut rng = SplitMix64::new(seed);
        let a = campaign_normal_f64(&mut rng);
        let b = campaign_normal_f64(&mut rng);
        let r = py_max(a, b);
        assert!(
            r.to_bits() == a.to_bits() || r.to_bits() == b.to_bits(),
            "py_max({a},{b})={r} neither a nor b (seed={seed})"
        );
    }

    /// P3: For non-NaN inputs, py_max is commutative.
    fn p3_py_max_commutative_for_finite_impl(seed: u64) {
        let mut rng = SplitMix64::new(seed);
        let a = campaign_normal_f64(&mut rng);
        let b = campaign_normal_f64(&mut rng);
        assert_eq!(py_max(a, b), py_max(b, a), "seed={seed}");
    }

    // --- BEGIN generated seeded property-mirror wrappers (deterministic proptest mirrors, R19/U6) ---
    // 3 properties x 20 seeds = 60 distinct-input wasm tests.
    #[cfg_attr(test, test)]
    fn p1_py_max_returns_larger_seed_000() { p1_py_max_returns_larger_impl(0); }
    #[cfg_attr(test, test)]
    fn p1_py_max_returns_larger_seed_001() { p1_py_max_returns_larger_impl(1); }
    #[cfg_attr(test, test)]
    fn p1_py_max_returns_larger_seed_002() { p1_py_max_returns_larger_impl(2); }
    #[cfg_attr(test, test)]
    fn p1_py_max_returns_larger_seed_003() { p1_py_max_returns_larger_impl(3); }
    #[cfg_attr(test, test)]
    fn p1_py_max_returns_larger_seed_004() { p1_py_max_returns_larger_impl(4); }
    #[cfg_attr(test, test)]
    fn p1_py_max_returns_larger_seed_005() { p1_py_max_returns_larger_impl(5); }
    #[cfg_attr(test, test)]
    fn p1_py_max_returns_larger_seed_006() { p1_py_max_returns_larger_impl(6); }
    #[cfg_attr(test, test)]
    fn p1_py_max_returns_larger_seed_007() { p1_py_max_returns_larger_impl(7); }
    #[cfg_attr(test, test)]
    fn p1_py_max_returns_larger_seed_008() { p1_py_max_returns_larger_impl(8); }
    #[cfg_attr(test, test)]
    fn p1_py_max_returns_larger_seed_009() { p1_py_max_returns_larger_impl(9); }
    #[cfg_attr(test, test)]
    fn p1_py_max_returns_larger_seed_010() { p1_py_max_returns_larger_impl(10); }
    #[cfg_attr(test, test)]
    fn p1_py_max_returns_larger_seed_011() { p1_py_max_returns_larger_impl(11); }
    #[cfg_attr(test, test)]
    fn p1_py_max_returns_larger_seed_012() { p1_py_max_returns_larger_impl(12); }
    #[cfg_attr(test, test)]
    fn p1_py_max_returns_larger_seed_013() { p1_py_max_returns_larger_impl(13); }
    #[cfg_attr(test, test)]
    fn p1_py_max_returns_larger_seed_014() { p1_py_max_returns_larger_impl(14); }
    #[cfg_attr(test, test)]
    fn p1_py_max_returns_larger_seed_015() { p1_py_max_returns_larger_impl(15); }
    #[cfg_attr(test, test)]
    fn p1_py_max_returns_larger_seed_016() { p1_py_max_returns_larger_impl(16); }
    #[cfg_attr(test, test)]
    fn p1_py_max_returns_larger_seed_017() { p1_py_max_returns_larger_impl(17); }
    #[cfg_attr(test, test)]
    fn p1_py_max_returns_larger_seed_018() { p1_py_max_returns_larger_impl(18); }
    #[cfg_attr(test, test)]
    fn p1_py_max_returns_larger_seed_019() { p1_py_max_returns_larger_impl(19); }
    #[cfg_attr(test, test)]
    fn p2_py_max_returns_one_of_inputs_seed_000() { p2_py_max_returns_one_of_inputs_impl(0); }
    #[cfg_attr(test, test)]
    fn p2_py_max_returns_one_of_inputs_seed_001() { p2_py_max_returns_one_of_inputs_impl(1); }
    #[cfg_attr(test, test)]
    fn p2_py_max_returns_one_of_inputs_seed_002() { p2_py_max_returns_one_of_inputs_impl(2); }
    #[cfg_attr(test, test)]
    fn p2_py_max_returns_one_of_inputs_seed_003() { p2_py_max_returns_one_of_inputs_impl(3); }
    #[cfg_attr(test, test)]
    fn p2_py_max_returns_one_of_inputs_seed_004() { p2_py_max_returns_one_of_inputs_impl(4); }
    #[cfg_attr(test, test)]
    fn p2_py_max_returns_one_of_inputs_seed_005() { p2_py_max_returns_one_of_inputs_impl(5); }
    #[cfg_attr(test, test)]
    fn p2_py_max_returns_one_of_inputs_seed_006() { p2_py_max_returns_one_of_inputs_impl(6); }
    #[cfg_attr(test, test)]
    fn p2_py_max_returns_one_of_inputs_seed_007() { p2_py_max_returns_one_of_inputs_impl(7); }
    #[cfg_attr(test, test)]
    fn p2_py_max_returns_one_of_inputs_seed_008() { p2_py_max_returns_one_of_inputs_impl(8); }
    #[cfg_attr(test, test)]
    fn p2_py_max_returns_one_of_inputs_seed_009() { p2_py_max_returns_one_of_inputs_impl(9); }
    #[cfg_attr(test, test)]
    fn p2_py_max_returns_one_of_inputs_seed_010() { p2_py_max_returns_one_of_inputs_impl(10); }
    #[cfg_attr(test, test)]
    fn p2_py_max_returns_one_of_inputs_seed_011() { p2_py_max_returns_one_of_inputs_impl(11); }
    #[cfg_attr(test, test)]
    fn p2_py_max_returns_one_of_inputs_seed_012() { p2_py_max_returns_one_of_inputs_impl(12); }
    #[cfg_attr(test, test)]
    fn p2_py_max_returns_one_of_inputs_seed_013() { p2_py_max_returns_one_of_inputs_impl(13); }
    #[cfg_attr(test, test)]
    fn p2_py_max_returns_one_of_inputs_seed_014() { p2_py_max_returns_one_of_inputs_impl(14); }
    #[cfg_attr(test, test)]
    fn p2_py_max_returns_one_of_inputs_seed_015() { p2_py_max_returns_one_of_inputs_impl(15); }
    #[cfg_attr(test, test)]
    fn p2_py_max_returns_one_of_inputs_seed_016() { p2_py_max_returns_one_of_inputs_impl(16); }
    #[cfg_attr(test, test)]
    fn p2_py_max_returns_one_of_inputs_seed_017() { p2_py_max_returns_one_of_inputs_impl(17); }
    #[cfg_attr(test, test)]
    fn p2_py_max_returns_one_of_inputs_seed_018() { p2_py_max_returns_one_of_inputs_impl(18); }
    #[cfg_attr(test, test)]
    fn p2_py_max_returns_one_of_inputs_seed_019() { p2_py_max_returns_one_of_inputs_impl(19); }
    #[cfg_attr(test, test)]
    fn p3_py_max_commutative_for_finite_seed_000() { p3_py_max_commutative_for_finite_impl(0); }
    #[cfg_attr(test, test)]
    fn p3_py_max_commutative_for_finite_seed_001() { p3_py_max_commutative_for_finite_impl(1); }
    #[cfg_attr(test, test)]
    fn p3_py_max_commutative_for_finite_seed_002() { p3_py_max_commutative_for_finite_impl(2); }
    #[cfg_attr(test, test)]
    fn p3_py_max_commutative_for_finite_seed_003() { p3_py_max_commutative_for_finite_impl(3); }
    #[cfg_attr(test, test)]
    fn p3_py_max_commutative_for_finite_seed_004() { p3_py_max_commutative_for_finite_impl(4); }
    #[cfg_attr(test, test)]
    fn p3_py_max_commutative_for_finite_seed_005() { p3_py_max_commutative_for_finite_impl(5); }
    #[cfg_attr(test, test)]
    fn p3_py_max_commutative_for_finite_seed_006() { p3_py_max_commutative_for_finite_impl(6); }
    #[cfg_attr(test, test)]
    fn p3_py_max_commutative_for_finite_seed_007() { p3_py_max_commutative_for_finite_impl(7); }
    #[cfg_attr(test, test)]
    fn p3_py_max_commutative_for_finite_seed_008() { p3_py_max_commutative_for_finite_impl(8); }
    #[cfg_attr(test, test)]
    fn p3_py_max_commutative_for_finite_seed_009() { p3_py_max_commutative_for_finite_impl(9); }
    #[cfg_attr(test, test)]
    fn p3_py_max_commutative_for_finite_seed_010() { p3_py_max_commutative_for_finite_impl(10); }
    #[cfg_attr(test, test)]
    fn p3_py_max_commutative_for_finite_seed_011() { p3_py_max_commutative_for_finite_impl(11); }
    #[cfg_attr(test, test)]
    fn p3_py_max_commutative_for_finite_seed_012() { p3_py_max_commutative_for_finite_impl(12); }
    #[cfg_attr(test, test)]
    fn p3_py_max_commutative_for_finite_seed_013() { p3_py_max_commutative_for_finite_impl(13); }
    #[cfg_attr(test, test)]
    fn p3_py_max_commutative_for_finite_seed_014() { p3_py_max_commutative_for_finite_impl(14); }
    #[cfg_attr(test, test)]
    fn p3_py_max_commutative_for_finite_seed_015() { p3_py_max_commutative_for_finite_impl(15); }
    #[cfg_attr(test, test)]
    fn p3_py_max_commutative_for_finite_seed_016() { p3_py_max_commutative_for_finite_impl(16); }
    #[cfg_attr(test, test)]
    fn p3_py_max_commutative_for_finite_seed_017() { p3_py_max_commutative_for_finite_impl(17); }
    #[cfg_attr(test, test)]
    fn p3_py_max_commutative_for_finite_seed_018() { p3_py_max_commutative_for_finite_impl(18); }
    #[cfg_attr(test, test)]
    fn p3_py_max_commutative_for_finite_seed_019() { p3_py_max_commutative_for_finite_impl(19); }
    // --- END generated seeded property-mirror wrappers ---

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("grid_stage::tests::py_max_nan_first_argument_wins", py_max_nan_first_argument_wins),
        ("grid_stage::tests::py_max_ties_keep_first", py_max_ties_keep_first),
        ("grid_stage::tests::py_max_infinity", py_max_infinity),
        ("grid_stage::tests::inner_layer_logic", inner_layer_logic),
        ("grid_stage::tests::p1_py_max_returns_larger_seed_000", p1_py_max_returns_larger_seed_000),
        ("grid_stage::tests::p1_py_max_returns_larger_seed_001", p1_py_max_returns_larger_seed_001),
        ("grid_stage::tests::p1_py_max_returns_larger_seed_002", p1_py_max_returns_larger_seed_002),
        ("grid_stage::tests::p1_py_max_returns_larger_seed_003", p1_py_max_returns_larger_seed_003),
        ("grid_stage::tests::p1_py_max_returns_larger_seed_004", p1_py_max_returns_larger_seed_004),
        ("grid_stage::tests::p1_py_max_returns_larger_seed_005", p1_py_max_returns_larger_seed_005),
        ("grid_stage::tests::p1_py_max_returns_larger_seed_006", p1_py_max_returns_larger_seed_006),
        ("grid_stage::tests::p1_py_max_returns_larger_seed_007", p1_py_max_returns_larger_seed_007),
        ("grid_stage::tests::p1_py_max_returns_larger_seed_008", p1_py_max_returns_larger_seed_008),
        ("grid_stage::tests::p1_py_max_returns_larger_seed_009", p1_py_max_returns_larger_seed_009),
        ("grid_stage::tests::p1_py_max_returns_larger_seed_010", p1_py_max_returns_larger_seed_010),
        ("grid_stage::tests::p1_py_max_returns_larger_seed_011", p1_py_max_returns_larger_seed_011),
        ("grid_stage::tests::p1_py_max_returns_larger_seed_012", p1_py_max_returns_larger_seed_012),
        ("grid_stage::tests::p1_py_max_returns_larger_seed_013", p1_py_max_returns_larger_seed_013),
        ("grid_stage::tests::p1_py_max_returns_larger_seed_014", p1_py_max_returns_larger_seed_014),
        ("grid_stage::tests::p1_py_max_returns_larger_seed_015", p1_py_max_returns_larger_seed_015),
        ("grid_stage::tests::p1_py_max_returns_larger_seed_016", p1_py_max_returns_larger_seed_016),
        ("grid_stage::tests::p1_py_max_returns_larger_seed_017", p1_py_max_returns_larger_seed_017),
        ("grid_stage::tests::p1_py_max_returns_larger_seed_018", p1_py_max_returns_larger_seed_018),
        ("grid_stage::tests::p1_py_max_returns_larger_seed_019", p1_py_max_returns_larger_seed_019),
        ("grid_stage::tests::p2_py_max_returns_one_of_inputs_seed_000", p2_py_max_returns_one_of_inputs_seed_000),
        ("grid_stage::tests::p2_py_max_returns_one_of_inputs_seed_001", p2_py_max_returns_one_of_inputs_seed_001),
        ("grid_stage::tests::p2_py_max_returns_one_of_inputs_seed_002", p2_py_max_returns_one_of_inputs_seed_002),
        ("grid_stage::tests::p2_py_max_returns_one_of_inputs_seed_003", p2_py_max_returns_one_of_inputs_seed_003),
        ("grid_stage::tests::p2_py_max_returns_one_of_inputs_seed_004", p2_py_max_returns_one_of_inputs_seed_004),
        ("grid_stage::tests::p2_py_max_returns_one_of_inputs_seed_005", p2_py_max_returns_one_of_inputs_seed_005),
        ("grid_stage::tests::p2_py_max_returns_one_of_inputs_seed_006", p2_py_max_returns_one_of_inputs_seed_006),
        ("grid_stage::tests::p2_py_max_returns_one_of_inputs_seed_007", p2_py_max_returns_one_of_inputs_seed_007),
        ("grid_stage::tests::p2_py_max_returns_one_of_inputs_seed_008", p2_py_max_returns_one_of_inputs_seed_008),
        ("grid_stage::tests::p2_py_max_returns_one_of_inputs_seed_009", p2_py_max_returns_one_of_inputs_seed_009),
        ("grid_stage::tests::p2_py_max_returns_one_of_inputs_seed_010", p2_py_max_returns_one_of_inputs_seed_010),
        ("grid_stage::tests::p2_py_max_returns_one_of_inputs_seed_011", p2_py_max_returns_one_of_inputs_seed_011),
        ("grid_stage::tests::p2_py_max_returns_one_of_inputs_seed_012", p2_py_max_returns_one_of_inputs_seed_012),
        ("grid_stage::tests::p2_py_max_returns_one_of_inputs_seed_013", p2_py_max_returns_one_of_inputs_seed_013),
        ("grid_stage::tests::p2_py_max_returns_one_of_inputs_seed_014", p2_py_max_returns_one_of_inputs_seed_014),
        ("grid_stage::tests::p2_py_max_returns_one_of_inputs_seed_015", p2_py_max_returns_one_of_inputs_seed_015),
        ("grid_stage::tests::p2_py_max_returns_one_of_inputs_seed_016", p2_py_max_returns_one_of_inputs_seed_016),
        ("grid_stage::tests::p2_py_max_returns_one_of_inputs_seed_017", p2_py_max_returns_one_of_inputs_seed_017),
        ("grid_stage::tests::p2_py_max_returns_one_of_inputs_seed_018", p2_py_max_returns_one_of_inputs_seed_018),
        ("grid_stage::tests::p2_py_max_returns_one_of_inputs_seed_019", p2_py_max_returns_one_of_inputs_seed_019),
        ("grid_stage::tests::p3_py_max_commutative_for_finite_seed_000", p3_py_max_commutative_for_finite_seed_000),
        ("grid_stage::tests::p3_py_max_commutative_for_finite_seed_001", p3_py_max_commutative_for_finite_seed_001),
        ("grid_stage::tests::p3_py_max_commutative_for_finite_seed_002", p3_py_max_commutative_for_finite_seed_002),
        ("grid_stage::tests::p3_py_max_commutative_for_finite_seed_003", p3_py_max_commutative_for_finite_seed_003),
        ("grid_stage::tests::p3_py_max_commutative_for_finite_seed_004", p3_py_max_commutative_for_finite_seed_004),
        ("grid_stage::tests::p3_py_max_commutative_for_finite_seed_005", p3_py_max_commutative_for_finite_seed_005),
        ("grid_stage::tests::p3_py_max_commutative_for_finite_seed_006", p3_py_max_commutative_for_finite_seed_006),
        ("grid_stage::tests::p3_py_max_commutative_for_finite_seed_007", p3_py_max_commutative_for_finite_seed_007),
        ("grid_stage::tests::p3_py_max_commutative_for_finite_seed_008", p3_py_max_commutative_for_finite_seed_008),
        ("grid_stage::tests::p3_py_max_commutative_for_finite_seed_009", p3_py_max_commutative_for_finite_seed_009),
        ("grid_stage::tests::p3_py_max_commutative_for_finite_seed_010", p3_py_max_commutative_for_finite_seed_010),
        ("grid_stage::tests::p3_py_max_commutative_for_finite_seed_011", p3_py_max_commutative_for_finite_seed_011),
        ("grid_stage::tests::p3_py_max_commutative_for_finite_seed_012", p3_py_max_commutative_for_finite_seed_012),
        ("grid_stage::tests::p3_py_max_commutative_for_finite_seed_013", p3_py_max_commutative_for_finite_seed_013),
        ("grid_stage::tests::p3_py_max_commutative_for_finite_seed_014", p3_py_max_commutative_for_finite_seed_014),
        ("grid_stage::tests::p3_py_max_commutative_for_finite_seed_015", p3_py_max_commutative_for_finite_seed_015),
        ("grid_stage::tests::p3_py_max_commutative_for_finite_seed_016", p3_py_max_commutative_for_finite_seed_016),
        ("grid_stage::tests::p3_py_max_commutative_for_finite_seed_017", p3_py_max_commutative_for_finite_seed_017),
        ("grid_stage::tests::p3_py_max_commutative_for_finite_seed_018", p3_py_max_commutative_for_finite_seed_018),
        ("grid_stage::tests::p3_py_max_commutative_for_finite_seed_019", p3_py_max_commutative_for_finite_seed_019),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}

// `proptest` is a dev-dependency (present under `cargo test`, absent from the
// ordinary non-test build `wasm_test_registry.rs` compiles into), so these
// three properties live in their own `#[cfg(test)]` sibling module -- exactly
// the split `copper_length.rs`/`timing.rs`/`host_math.rs` already use --
// rather than inline inside `tests` above, so `gen_wasm_test_registry.py`'s
// per-module `proptest-dev-dependency` exclusion only drops these three
// properties instead of the whole module's otherwise-pure `py_max` tests.
#[cfg(test)]
mod proptests {
    use super::*;
    use proptest::prelude::*;

    /// P1: py_max returns the conventional maximum for non-NaN f64 values.
    #[test]
    fn p1_py_max_returns_larger() {
        proptest!(|(a: f64, b: f64)| {
            prop_assume!(!a.is_nan() && !b.is_nan());
            let r = py_max(a, b);
            assert!(r >= a && r >= b,
                "py_max({a},{b})={r} not >= both");
        });
    }

    /// P2: py_max returns one of its arguments (bit-identical).
    #[test]
    fn p2_py_max_returns_one_of_inputs() {
        proptest!(|(a: f64, b: f64)| {
            let r = py_max(a, b);
            // For NaN inputs, either both are NaN (then r is NaN, bits match)
            // or first-arg-wins (a.is_nan() => r.is_nan(), !b.is_nan() => r bits==b bits).
            if a.is_nan() {
                // First arg is NaN -> result is NaN regardless of second arg.
                assert!(r.is_nan());
            } else if b.is_nan() {
                // Second arg is NaN, first arg wins.
                assert_eq!(r.to_bits(), a.to_bits());
            } else {
                assert!(r.to_bits() == a.to_bits() || r.to_bits() == b.to_bits(),
                    "py_max({a},{b})={r} neither a nor b");
            }
        });
    }

    /// P3: For non-NaN inputs, py_max is commutative.
    #[test]
    fn p3_py_max_commutative_for_finite() {
        proptest!(|(a: f64, b: f64)| {
            prop_assume!(!a.is_nan() && !b.is_nan());
            assert_eq!(py_max(a, b), py_max(b, a));
        });
    }
}
