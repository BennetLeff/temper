// The D7 `FinePitchEscapeStage` of the Rust Orchestration Engine plan
// (2026-08-09-001, Phase D batch D7): a `Stage<BoardState>` implementor
// mirroring `deterministic/stages/fine_pitch_escape.py`.
//
// The run() orchestration moves to Rust: the `if not state.netlist` guard,
// the fine-pitch detection passes (min-pin-pitch kernel + net collection),
// the escape-via placement loop (via-position dedup on the
// CPython-`round(x, 3)` keys, escape-layer selection, `Via` construction),
// the debug prints, and the Phase-5 escape validation + auto-generation.
// The leaf kernels stay single-source and are driven through FFI:
// `temper_design_bundle_python.deterministic_leaves` (`min_pin_pitch_py` /
// `escape_layer_for_net_py`) and `temper_placer.core.pin_geometry`
// (`pin_world_position_at`). The `Via` pyclass stays Python (constructed
// through FFI). The Python stage instance is the config carrier (the
// D4/D5/D6 pattern): `pin_pitch_threshold_mm` / `escape_layer` /
// `secondary_escape_layer` / `via_drill_mm` / `via_diameter_mm` /
// `layer2_nets` / `layer3_nets` are read back off it; the stage's
// `_calculate_min_pin_pitch` / `_get_escape_layer_for_net` methods stay on
// the Python shim as directly-exercised public API (the port calls the same
// kernels, so the differential pins the two agree).
//
// Bit-exactness notes:
// - `round(pin_x, 3)` is CPython `round` (round-half-to-even) on the
//   ORIGINAL float, called through builtins -- never Rust `f64::round`.
// - Every `print` message renders through CPython `str.format` (David-Gay
//   `:.2f`, float `str()`, `sorted()` list reprs) -- parity by identity.

#[cfg(feature = "python")]
use std::borrow::Cow;

#[cfg(feature = "python")]
use pyo3::prelude::*;
#[cfg(feature = "python")]
use pyo3::types::{PyDict, PyList, PyString, PyTuple};

#[cfg(feature = "python")]
use std::collections::HashSet;

#[cfg(feature = "python")]
use crate::board_state::{BoardState, ViaEntry};
#[cfg(feature = "python")]
use crate::d6_util;
#[cfg(feature = "python")]
use crate::derivation_stage::stage_guard;
#[cfg(feature = "python")]
use crate::stage::{Stage, StageError};
#[cfg(feature = "python")]
use temper_data_model::PlacementSet;

const STAGE_NAME: &str = "fine_pitch_escape";

#[cfg(feature = "python")]
/// The fine-pitch escape stage: netlist + placements -> `BoardState.vias`
/// with the fine-pitch escape vias appended.
#[derive(Debug, Clone)]
pub struct FinePitchEscapeStage {
    pub stage: Py<PyAny>,
}

#[cfg(feature = "python")]
impl Stage<BoardState> for FinePitchEscapeStage {
    fn name(&self) -> Cow<'static, str> {
        Cow::Borrowed(STAGE_NAME)
    }

    fn run(&self, state: BoardState) -> Result<BoardState, StageError> {
        stage_guard(STAGE_NAME, || {
            Python::attach(|py| {
                let to_stage = |e: pyo3::PyErr| crate::derivation_stage::pyerr_stage(STAGE_NAME, e);
                self.run_inner(py, state).map_err(to_stage)
            })
        })
    }
}

#[cfg(feature = "python")]
impl FinePitchEscapeStage {
    fn run_inner(&self, py: Python<'_>, state: BoardState) -> PyResult<BoardState> {
        let netlist = match &state.netlist {
            Some(n) if n.bind(py).is_truthy()? => n.bind(py).clone(),
            _ => return Ok(state),
        };
        let stage = self.stage.bind(py);
        let threshold: f64 = stage.getattr("pin_pitch_threshold_mm")?.extract()?;
        let via_drill: f64 = stage.getattr("via_drill_mm")?.extract()?;
        let via_diameter: f64 = stage.getattr("via_diameter_mm")?.extract()?;
        let layer2_nets = stage.getattr("layer2_nets")?;
        let layer3_nets = stage.getattr("layer3_nets")?;
        let escape_layer: i64 = stage.getattr("escape_layer")?.extract()?;
        let secondary_escape_layer: i64 = stage.getattr("secondary_escape_layer")?.extract()?;

        // `placements = dict(state.placements) if state.placements else {}`.
        // U6 (O-C3) group-2: the owned `PlacementSet` is rebuilt into the
        // Python frozenset, then `dict(...)`-ed exactly like the oracle.
        let placements_dict: Py<PyDict> = match &state.placements {
            Some(p) if !p.is_empty() => {
                let fs = crate::marshal::to_python::<PlacementSet>(py, p)?;
                py.import("builtins")?
                    .getattr("dict")?
                    .call1((fs,))?
                    .extract()?
            }
            _ => PyDict::new(py).unbind(),
        };
        let placements_dict = placements_dict.bind(py);

        // `vias = list(state.vias) if state.vias else []`.
        let vias = match &state.vias {
            Some(v) if !v.is_empty() => {
                let fs = crate::marshal::to_python::<HashSet<ViaEntry>>(py, v)?;
                py.import("builtins")?.getattr("list")?.call1((fs,))?
            }
            _ => PyList::empty(py).into_any(),
        };

        let leaves = py
            .import("temper_design_bundle_python")?
            .getattr("deterministic_leaves")?;
        let pin_geometry = py.import("temper_placer.core.pin_geometry")?;
        let builtins = py.import("builtins")?;
        let round_ = builtins.getattr("round")?;
        let set_ = builtins.getattr("set")?;
        let via_cls = py.import("temper_placer.core.board")?.getattr("Via")?;

        // ---- First pass: identify fine-pitch components + their nets ----
        let fine_pitch_refs = set_.call0()?;
        let fine_pitch_nets = set_.call0()?;
        let mut fine_pitch_components: Vec<(String, f64, usize)> = Vec::new();

        for component in netlist.getattr("components")?.try_iter()? {
            let component = component?;
            // `min_pitch = self._calculate_min_pin_pitch(component)`.
            let min_pitch: Option<f64> = leaves
                .call_method1("min_pin_pitch_py", (component.getattr("pins")?,))?
                .extract()?;
            if let Some(min_pitch) = min_pitch
                && min_pitch < threshold
            {
                let ref_: String = component.getattr("ref")?.extract()?;
                let n_pins = component.getattr("pins")?.len()?;
                fine_pitch_refs.call_method1("add", (component.getattr("ref")?,))?;
                fine_pitch_components.push((ref_, min_pitch, n_pins));
                for pin in component.getattr("pins")?.try_iter()? {
                    let pin = pin?;
                    let net = pin.getattr("net")?;
                    if net.is_truthy()? {
                        fine_pitch_nets.call_method1("add", (net,))?;
                    }
                }
            }
        }

        // ---- Second pass: place escape vias ----
        let via_positions = set_.call0()?;
        let mut layer1_vias = 0i64;
        let mut layer2_vias = 0i64;
        let mut layer3_vias = 0i64;

        for component in netlist.getattr("components")?.try_iter()? {
            let component = component?;
            // `comp_pos = placements.get(component.ref, component.initial_position)`.
            let comp_pos = match placements_dict.get_item(component.getattr("ref")?)? {
                Some(pos) => pos,
                None => component.getattr("initial_position")?,
            };
            if comp_pos.is_none() {
                continue;
            }

            for pin in component.getattr("pins")?.try_iter()? {
                let pin = pin?;
                let net = pin.getattr("net")?;
                if !net.is_truthy()? {
                    continue; // Skip NC pins
                }
                // `if component.ref not in fine_pitch_refs and pin.net not
                // in fine_pitch_nets: continue`.
                let in_fp_refs =
                    fine_pitch_refs.call_method1("__contains__", (component.getattr("ref")?,))?;
                let in_fp_nets = fine_pitch_nets.call_method1("__contains__", (&net,))?;
                if !in_fp_refs.is_truthy()? && !in_fp_nets.is_truthy()? {
                    continue;
                }

                // `pin_x, pin_y = pin_world_position_at(pin, component, comp_pos)`.
                let world = pin_geometry
                    .call_method1("pin_world_position_at", (&pin, &component, &comp_pos))?;
                let pin_x: f64 = world.get_item(0)?.extract()?;
                let pin_y: f64 = world.get_item(1)?.extract()?;

                // `pos_key = (round(pin_x, 3), round(pin_y, 3))` -- CPython
                // round (round-half-to-even).
                let key = PyTuple::new(py, [round_.call1((pin_x, 3))?, round_.call1((pin_y, 3))?])?;
                let contains = via_positions.call_method1("__contains__", (&key,))?;
                if contains.is_truthy()? {
                    continue;
                }
                via_positions.call_method1("add", (&key,))?;

                // `escape_layer_num, escape_layer_name =
                // self._get_escape_layer_for_net(pin.net)`.
                let (escape_layer_num, escape_layer_name): (i64, String) = leaves
                    .call_method1(
                        "escape_layer_for_net_py",
                        (
                            &net,
                            &layer2_nets,
                            &layer3_nets,
                            escape_layer,
                            secondary_escape_layer,
                        ),
                    )?
                    .extract()?;

                // `via = Via(position=(pin_x, pin_y), drill=..., width=...,
                // layers=("F.Cu", escape_layer_name), net=pin.net)`.
                let layers = PyTuple::new(
                    py,
                    [
                        PyString::new(py, "F.Cu").into_any(),
                        PyString::new(py, &escape_layer_name).into_any(),
                    ],
                )?;
                let kwargs = PyDict::new(py);
                kwargs.set_item("position", PyTuple::new(py, [pin_x, pin_y])?)?;
                kwargs.set_item("drill", via_drill)?;
                kwargs.set_item("width", via_diameter)?;
                kwargs.set_item("layers", &layers)?;
                kwargs.set_item("net", &net)?;
                let via = via_cls.call((), Some(&kwargs))?;
                vias.call_method1("append", (via,))?;

                if escape_layer_num == 1 {
                    layer1_vias += 1;
                } else if escape_layer_num == 2 {
                    layer2_vias += 1;
                } else {
                    // layer 3 (B.Cu)
                    layer3_vias += 1;
                }
            }
        }

        // ---- Debug output ----
        let n_fp = fine_pitch_components.len();
        if n_fp > 0 {
            py_print_fmt(
                py,
                "  Fine-pitch components detected: {}",
                &[n_fp.into_pyobject(py)?.into_any()],
            )?;
            for (ref_, pitch, pin_count) in &fine_pitch_components {
                // `comp = next((c for c in state.netlist.components if
                // c.ref == ref), None)`.
                let mut netted_pins: usize = 0;
                for comp in netlist.getattr("components")?.try_iter()? {
                    let comp = comp?;
                    let comp_ref: String = comp.getattr("ref")?.extract()?;
                    if &comp_ref == ref_ {
                        for pin in comp.getattr("pins")?.try_iter()? {
                            let pin = pin?;
                            if pin.getattr("net")?.is_truthy()? {
                                netted_pins += 1;
                            }
                        }
                        break;
                    }
                }
                py_print_fmt(
                    py,
                    "    {}: min_pitch={:.2f}mm, {}/{} pins with nets",
                    &[
                        PyString::new(py, ref_).into_any(),
                        (*pitch).into_pyobject(py)?.into_any(),
                        netted_pins.into_pyobject(py)?.into_any(),
                        (*pin_count).into_pyobject(py)?.into_any(),
                    ],
                )?;
            }
            py_print_fmt(
                py,
                "  Nets touching fine-pitch components: {}",
                &[fine_pitch_nets.len()?.into_pyobject(py)?.into_any()],
            )?;
            py_print_fmt(
                py,
                "  Escape vias: {} to In1.Cu, {} to In2.Cu, {} to B.Cu",
                &[
                    layer1_vias.into_pyobject(py)?.into_any(),
                    layer2_vias.into_pyobject(py)?.into_any(),
                    layer3_vias.into_pyobject(py)?.into_any(),
                ],
            )?;
            if layer2_nets.is_truthy()? {
                let sorted2 = builtins.getattr("sorted")?.call1((&layer2_nets,))?;
                py_print_fmt(py, "  Layer 2 nets: {}", &[sorted2])?;
            }
            if layer3_nets.is_truthy()? {
                let sorted3 = builtins.getattr("sorted")?.call1((&layer3_nets,))?;
                py_print_fmt(py, "  Layer 3 (B.Cu) nets: {}", &[sorted3])?;
            }
        } else {
            py_print_fmt(
                py,
                "  No fine-pitch components detected (threshold: {}mm)",
                &[threshold.into_pyobject(py)?.into_any()],
            )?;
        }

        // ---- PHASE 5: escape validation + auto-generation ----
        if fine_pitch_refs.len()? > 0 {
            let missing_escapes = PyList::empty(py);
            let current_via_positions = set_.call0()?;
            for v in vias.try_iter()? {
                let v = v?;
                let pos = v.getattr("position")?;
                let key = PyTuple::new(
                    py,
                    [
                        round_.call1((pos.get_item(0)?, 3))?,
                        round_.call1((pos.get_item(1)?, 3))?,
                    ],
                )?;
                current_via_positions.call_method1("add", (&key,))?;
            }

            for component in netlist.getattr("components")?.try_iter()? {
                let component = component?;
                let ref_ = component.getattr("ref")?;
                let in_fp_refs = fine_pitch_refs.call_method1("__contains__", (&ref_,))?;
                if !in_fp_refs.is_truthy()? {
                    continue;
                }
                let comp_pos = match placements_dict.get_item(&ref_)? {
                    Some(pos) => pos,
                    None => component.getattr("initial_position")?,
                };
                if comp_pos.is_none() {
                    continue;
                }
                for pin in component.getattr("pins")?.try_iter()? {
                    let pin = pin?;
                    let net = pin.getattr("net")?;
                    if !net.is_truthy()? {
                        continue; // Skip NC pins
                    }
                    let world = pin_geometry
                        .call_method1("pin_world_position_at", (&pin, &component, &comp_pos))?;
                    let pin_x: f64 = world.get_item(0)?.extract()?;
                    let pin_y: f64 = world.get_item(1)?.extract()?;
                    let key =
                        PyTuple::new(py, [round_.call1((pin_x, 3))?, round_.call1((pin_y, 3))?])?;
                    let has = current_via_positions.call_method1("__contains__", (&key,))?;
                    if !has.is_truthy()? {
                        let m = PyDict::new(py);
                        m.set_item("ref", &ref_)?;
                        m.set_item("pin", pin.getattr("name")?)?;
                        m.set_item("net", &net)?;
                        let pos_t = PyTuple::new(py, [pin_x, pin_y])?;
                        m.set_item("pos", &pos_t)?;
                        missing_escapes.append(m)?;
                    }
                }
            }

            if missing_escapes.len() > 0 {
                py_print_fmt(
                    py,
                    "\n  [EscapeValidation] Found {} fine-pitch pins missing escape vias",
                    &[missing_escapes.len().into_pyobject(py)?.into_any()],
                )?;

                // `by_net` grouping, then the top-10 by group size.
                let mut by_net: Vec<(String, Vec<Bound<'_, PyAny>>)> = Vec::new();
                for m in missing_escapes.try_iter()? {
                    let m = m?;
                    let net: String = m.get_item("net")?.extract()?;
                    match by_net.iter_mut().find(|(name, _)| *name == net) {
                        Some((_, entries)) => entries.push(m),
                        None => by_net.push((net, vec![m])),
                    }
                }
                by_net.sort_by_key(|(_, entries)| std::cmp::Reverse(entries.len()));
                for (net, entries) in by_net.into_iter().take(10) {
                    let mut pin_list = String::new();
                    for (i, p) in entries.iter().take(3).enumerate() {
                        let ref_ = p.get_item("ref")?.str()?;
                        let pin = p.get_item("pin")?.str()?;
                        if i > 0 {
                            pin_list.push_str(", ");
                        }
                        pin_list.push_str(&ref_.to_string_lossy());
                        pin_list.push('.');
                        pin_list.push_str(&pin.to_string_lossy());
                    }
                    if entries.len() > 3 {
                        pin_list.push_str(&format!(" (+{} more)", entries.len() - 3));
                    }
                    py_print_fmt(
                        py,
                        "    {}: {}",
                        &[
                            PyString::new(py, &net).into_any(),
                            PyString::new(py, &pin_list).into_any(),
                        ],
                    )?;
                }

                // Auto-generate missing escapes.
                py_print_fmt(
                    py,
                    "\n  [EscapeValidation] Auto-generating {} missing escape vias...",
                    &[missing_escapes.len().into_pyobject(py)?.into_any()],
                )?;
                let mut generated_count = 0i64;
                for m in missing_escapes.try_iter()? {
                    let m = m?;
                    let pin_pos = m.get_item("pos")?;
                    let net_name = m.get_item("net")?;
                    let key = PyTuple::new(
                        py,
                        [
                            round_.call1((pin_pos.get_item(0)?, 3))?,
                            round_.call1((pin_pos.get_item(1)?, 3))?,
                        ],
                    )?;
                    let has = current_via_positions.call_method1("__contains__", (&key,))?;
                    if has.is_truthy()? {
                        continue;
                    }
                    let (escape_layer_num, escape_layer_name): (i64, String) = leaves
                        .call_method1(
                            "escape_layer_for_net_py",
                            (
                                &net_name,
                                &layer2_nets,
                                &layer3_nets,
                                escape_layer,
                                secondary_escape_layer,
                            ),
                        )?
                        .extract()?;
                    let layers = PyTuple::new(
                        py,
                        [
                            PyString::new(py, "F.Cu").into_any(),
                            PyString::new(py, &escape_layer_name).into_any(),
                        ],
                    )?;
                    let kwargs = PyDict::new(py);
                    kwargs.set_item("position", &pin_pos)?;
                    kwargs.set_item("drill", via_drill)?;
                    kwargs.set_item("width", via_diameter)?;
                    kwargs.set_item("layers", &layers)?;
                    kwargs.set_item("net", &net_name)?;
                    let via = via_cls.call((), Some(&kwargs))?;
                    vias.call_method1("append", (via,))?;
                    current_via_positions.call_method1("add", (&key,))?;
                    generated_count += 1;

                    if escape_layer_num == 1 {
                        layer1_vias += 1;
                    } else if escape_layer_num == 2 {
                        layer2_vias += 1;
                    } else if escape_layer_num == 3 {
                        layer3_vias += 1;
                    }
                }

                py_print_fmt(
                    py,
                    "    Added {} escape vias",
                    &[generated_count.into_pyobject(py)?.into_any()],
                )?;
                py_print_fmt(
                    py,
                    "  Updated totals: {} to In1.Cu, {} to In2.Cu, {} to B.Cu",
                    &[
                        layer1_vias.into_pyobject(py)?.into_any(),
                        layer2_vias.into_pyobject(py)?.into_any(),
                        layer3_vias.into_pyobject(py)?.into_any(),
                    ],
                )?;
            }
        }

        // `return replace(state, vias=frozenset(vias))`.
        let frozenset_ = builtins.getattr("frozenset")?;
        let fs = frozenset_.call1((&vias,))?;
        let mut new_state = state;
        new_state.vias = Some(crate::marshal::to_owned::<HashSet<ViaEntry>>(&fs)?);
        Ok(new_state)
    }
}

#[cfg(feature = "python")]
/// `print(str.format(template, *args))` -- the only message renderer
/// (David-Gay `:.2f`, float `str()`, int/str interpolation, `sorted` list
/// reprs) stays CPython.
fn py_print_fmt(py: Python<'_>, template: &str, args: &[Bound<'_, PyAny>]) -> PyResult<()> {
    let rendered = d6_util::py_format(py, template, args)?;
    d6_util::py_print(py, &[rendered])
}

#[cfg(feature = "python")]
/// FFI entry for the Python shim: `run_fine_pitch_escape(state, stage)`.
#[pyfunction]
pub fn run_fine_pitch_escape(
    py: Python<'_>,
    state: Py<PyAny>,
    stage: Py<PyAny>,
) -> PyResult<Py<PyAny>> {
    let rust_state = crate::d1_bridge::from_python(py, state.bind(py))
        .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(format!("{STAGE_NAME}: {e}")))?;
    let rust_stage = FinePitchEscapeStage { stage };
    let out = rust_stage
        .run(rust_state)
        .map_err(|e| crate::config_attach_stage::to_pyerr(&e))?;
    crate::d1_bridge::to_python(py, state.bind(py), &out, &["vias"])
}
