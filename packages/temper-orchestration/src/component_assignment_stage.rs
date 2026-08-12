// The D4 `ComponentAssignmentStage` of the Rust Orchestration Engine plan
// (2026-08-09-001, Phase D batch D4): a `Stage<BoardState>` implementor
// mirroring `deterministic/stages/component_assignment.py`.
//
// The run() orchestration moves to Rust: the state guards
// (`if not state.netlist or not state.component_zone_map or not
// state.zone_slots: return state` -- identity preserved), `_domain_lookups`
// (per-ref domain map + the HV_edge/LV_interior region dict from
// `state.domain_regions`), the GEOS domain filter PRECOMPUTED into the
// per-ref `domain_ok` slot set (the loop structure and the
// `region.covers(Point(x, y))` predicate are driven here through the
// shapely objects at runtime -- shapely/GEOS itself stays Python), the
// sheetpath-first/ref-fallback fixed-placement resolution, the greedy-kernel
// call (`temper_design_bundle_python.deterministic_leaves.
// assign_components_to_slots`, the Wave-4 Phase-5 leaf kernel, called via
// runtime PyModule::import), the `dict(...)` wrap and the
// `frozenset(placements.items())` write into `BoardState.placements`.
//
// Bit-exactness notes:
// - `dict(state.component_zone_map)` / `dict(state.zone_slots)` are built
//   via the builtins `dict()` over the ORIGINAL frozenset objects, so the
//   dict insertion order is the frozenset's iteration order exactly like the
//   oracle (the kernel's cross-zone fallback scans the zone dict in that
//   order -- order is load-bearing).
// - `domain_ok` is keyed in netlist component order with explicit
//   de-duplication (`seen_refs`), and each entry's covered slot SET is
//   built by iterating `zone_slots.items()` in dict order, exactly like the
//   oracle's set comprehension (the set content is order-independent, but
//   the membership predicate and the dedup are the observable contract).
// - The fixed-placement `float(pos[i])` conversions extract via pyo3's f64
//   (int -> float is exact; the phase-5 kernel pins the same conversions).
// - `frozenset(placements.items())` goes through the builtins `frozenset`
//   on the kernel's dict-items view.

#[cfg(feature = "python")]
use std::borrow::Cow;
#[cfg(feature = "python")]
use std::collections::HashSet;

#[cfg(feature = "python")]
use pyo3::prelude::*;
#[cfg(feature = "python")]
use pyo3::types::{PyDict, PySet, PyTuple};

#[cfg(feature = "python")]
use crate::board_state::BoardState;
#[cfg(feature = "python")]
use crate::config_attach_stage::to_pyerr;
#[cfg(feature = "python")]
use crate::derivation_stage::{pyerr_stage, stage_guard};
#[cfg(feature = "python")]
use crate::stage::{Stage, StageError};

#[cfg(feature = "python")]
/// The component-assignment stage: netlist + zone maps + slot grid ->
/// `BoardState.placements` (frozenset of `(ref, (x, y))`).
#[derive(Debug, Clone)]
pub struct ComponentAssignmentStage {
    pub slot_spacing: f64,
    pub fixed_placements: Option<Py<PyAny>>,
}

#[cfg(feature = "python")]
impl Stage<BoardState> for ComponentAssignmentStage {
    fn name(&self) -> Cow<'static, str> {
        Cow::Borrowed("component_assignment")
    }

    fn run(&self, state: BoardState) -> Result<BoardState, StageError> {
        stage_guard("component_assignment", || {
            Python::attach(|py| {
                let to_stage = |e: pyo3::PyErr| pyerr_stage("component_assignment", e);
                self.run_inner(py, state).map_err(to_stage)
            })
        })
    }
}

#[cfg(feature = "python")]
impl ComponentAssignmentStage {
    /// The stage body. Returns the state unchanged (identity preserved) when
    /// the guard fires.
    fn run_inner(&self, py: Python<'_>, state: BoardState) -> PyResult<BoardState> {
        // `if not state.netlist or not state.component_zone_map or not
        // state.zone_slots: return state`
        let netlist = match &state.netlist {
            Some(n) if n.bind(py).is_truthy()? => n.clone_ref(py),
            _ => return Ok(state),
        };
        let component_zone_map = match &state.component_zone_map {
            Some(c) if c.bind(py).is_truthy()? => c.clone_ref(py),
            _ => return Ok(state),
        };
        let zone_slots = match &state.zone_slots {
            Some(z) if z.bind(py).is_truthy()? => z.clone_ref(py),
            _ => return Ok(state),
        };

        // dict(state.component_zone_map) / dict(state.zone_slots) -- the
        // frozensets rebuilt as dicts in frozenset iteration order.
        let czm_dict = builtins_dict(py, component_zone_map.bind(py))?;
        let zs_dict = builtins_dict(py, zone_slots.bind(py))?;

        let (domain_for_ref, domain_regions) = domain_lookups(py, &state)?;
        let placements = assign_inner(
            py,
            netlist.as_any(),
            &czm_dict,
            &zs_dict,
            &self.fixed_placements,
            &domain_for_ref,
            &domain_regions,
            self.slot_spacing,
        )?;

        // `frozenset(placements.items())`
        let items = placements.call_method0("items")?;
        let placements_fs = py
            .import("builtins")?
            .getattr("frozenset")?
            .call1((items,))?;

        let mut new_state = state;
        new_state.placements = Some(placements_fs.into_any().unbind());
        Ok(new_state)
    }
}

#[cfg(feature = "python")]
/// `_domain_lookups`: the per-ref domain map and the HV_edge/LV_interior
/// region dict. Both stay EMPTY dicts when the partition stage was disabled
/// (empty `component_domain_map` / `domain_regions` on the state).
fn domain_lookups<'py>(
    py: Python<'py>,
    state: &BoardState,
) -> PyResult<(Bound<'py, PyAny>, Bound<'py, PyAny>)> {
    let domain_for_ref = PyDict::new(py);
    let domain_regions = PyDict::new(py);
    let domain_map = match &state.component_domain_map {
        Some(d) if d.bind(py).is_truthy()? => d,
        _ => return Ok((domain_for_ref.into_any(), domain_regions.into_any())),
    };
    let regions = match &state.domain_regions {
        Some(r) if r.bind(py).is_truthy()? => r.bind(py),
        _ => return Ok((domain_for_ref.into_any(), domain_regions.into_any())),
    };
    // `for ref, domain in state.component_domain_map: domain_for_ref[ref] = domain`
    for pair in domain_map.bind(py).try_iter()? {
        let pair = pair?;
        let (r, d) = (pair.get_item(0)?, pair.get_item(1)?);
        domain_for_ref.set_item(&r, &d)?;
    }
    // `regions[0] -> "HV_edge", regions[1] -> "LV_interior"` for >= 2,
    // `regions[0] -> "LV_interior"` for exactly 1.
    let n_regions = regions.len()?;
    if n_regions >= 2 {
        domain_regions.set_item("HV_edge", regions.get_item(0)?)?;
        domain_regions.set_item("LV_interior", regions.get_item(1)?)?;
    } else if n_regions == 1 {
        domain_regions.set_item("LV_interior", regions.get_item(0)?)?;
    }
    Ok((domain_for_ref.into_any(), domain_regions.into_any()))
}

#[cfg(feature = "python")]
/// The `_assign_components_to_slots` orchestration: precompute the per-ref
/// `domain_ok` slot set (the GEOS filter), resolve fixed placements
/// (sheetpath-first, ref fallback) and call the greedy kernel. Returns the
/// placements DICT (the oracle's `dict(...)` wrap).
#[allow(clippy::too_many_arguments)]
fn assign_inner<'py>(
    py: Python<'py>,
    netlist: &Py<PyAny>,
    component_zone_map: &Bound<'py, PyAny>,
    zone_slots: &Bound<'py, PyAny>,
    fixed_placements: &Option<Py<PyAny>>,
    domain_for_ref: &Bound<'py, PyAny>,
    domain_regions: &Bound<'py, PyAny>,
    slot_spacing: f64,
) -> PyResult<Bound<'py, PyAny>> {
    let domain_ok = PyDict::new(py);
    let has_domains = domain_for_ref.len()? > 0 && domain_regions.len()? > 0;
    if has_domains {
        let shape_point = py
            .import("shapely.geometry")?
            .getattr("Point")?;
        let mut seen_refs: HashSet<String> = HashSet::new();
        for component in netlist.bind(py).getattr("components")?.try_iter()? {
            let component = component?;
            let ref_val = component.getattr("ref")?;
            let ref_name: String = ref_val.extract()?;
            if !seen_refs.insert(ref_name) {
                continue;
            }
            let domain = domain_for_ref.call_method1("get", (&ref_val,))?;
            if domain.is_none() {
                continue;
            }
            let region = domain_regions.call_method1("get", (&domain,))?;
            if region.is_none() {
                continue;
            }
            let is_empty: bool = region.getattr("is_empty")?.extract()?;
            if is_empty {
                continue;
            }
            // `covered = {s for _zone, slots in zone_slots.items()
            //             for s in slots if region.covers(Point(s[0], s[1]))}`
            let covered = PySet::empty(py)?;
            for (_zone, slots) in dict_items(py, zone_slots)? {
                for slot in slots.bind(py).try_iter()? {
                    let slot = slot?;
                    let point = shape_point.call1((slot.get_item(0)?, slot.get_item(1)?))?;
                    let covers: bool = region.call_method1("covers", (point,))?.extract()?;
                    if covers {
                        covered.add(slot)?;
                    }
                }
            }
            if covered.len() > 0 {
                domain_ok.set_item(&ref_val, covered)?;
            }
        }
    }

    // Fixed placements: `{c.ref: (x, y)}` resolved sheetpath-first then by
    // ref, exactly like the oracle, into a dict in `fixed_placements`
    // insertion order.
    let fixed = PyDict::new(py);
    if let Some(fp) = fixed_placements {
        let fp_bound = fp.bind(py);
        if fp_bound.is_truthy()? {
            let comp_by_ref = PyDict::new(py);
            let comp_by_sheetpath = PyDict::new(py);
            for component in netlist.bind(py).getattr("components")?.try_iter()? {
                let component = component?;
                comp_by_ref.set_item(component.getattr("ref")?, &component)?;
                let sheetpath = component.getattr("sheetpath")?;
                if !sheetpath.is_none() && sheetpath.is_truthy()? {
                    comp_by_sheetpath.set_item(sheetpath, &component)?;
                }
            }
            for (key, info) in dict_items(py, fp_bound)? {
                let key_bound = key.bind(py);
                let comp = match comp_by_sheetpath.get_item(key_bound)? {
                    Some(c) => c,
                    None => match comp_by_ref.get_item(key_bound)? {
                        Some(c) => c,
                        None => continue,
                    },
                };
                let pos: Option<Bound<'_, PyAny>> = {
                    let info_bound = info.bind(py);
                    let is_seq = info_bound.is_instance_of::<pyo3::types::PyList>()
                        || info_bound.is_instance_of::<PyTuple>();
                    if is_seq && info_bound.len()? == 2 {
                        Some(info_bound.clone())
                    } else if info_bound.is_instance_of::<PyDict>() {
                        let v = info_bound.call_method1("get", ("position",))?;
                        if v.is_none() {
                            None
                        } else {
                            Some(v)
                        }
                    } else {
                        None
                    }
                };
                if let Some(pos) = pos
                    && pos.len()? == 2
                {
                    let x: f64 = pos.get_item(0)?.extract()?;
                    let y: f64 = pos.get_item(1)?.extract()?;
                    fixed.set_item(comp.getattr("ref")?, (x, y))?;
                }
            }
        }
    }

    // The greedy kernel + the oracle's `dict(...)` wrap.
    let tdb = py
        .import("temper_design_bundle_python")?
        .getattr("deterministic_leaves")?;
    let result = tdb.call_method1(
        "assign_components_to_slots",
        (
            netlist,
            component_zone_map,
            zone_slots,
            fixed,
            domain_ok,
            slot_spacing,
        ),
    )?;
    builtins_dict(py, &result)
}

#[cfg(feature = "python")]
/// `dict(obj)` -- the builtin dict constructor over an iterable of pairs.
fn builtins_dict<'py>(
    py: Python<'py>,
    obj: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    py.import("builtins")?
        .getattr("dict")?
        .call1((obj,))
}

#[cfg(feature = "python")]
/// `dict.items()` in insertion order.
fn dict_items<'py>(
    py: Python<'py>,
    dict: &Bound<'py, PyAny>,
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
/// FFI entry for the Python shim: `run_component_assignment(state,
/// slot_spacing, fixed_placements)`.
#[pyfunction]
#[pyo3(signature = (state, slot_spacing, fixed_placements))]
pub fn run_component_assignment(
    py: Python<'_>,
    state: Py<PyAny>,
    slot_spacing: f64,
    fixed_placements: Option<Py<PyAny>>,
) -> PyResult<Py<PyAny>> {
    let rust_state = crate::d1_bridge::from_python(py, state.bind(py)).map_err(|e| {
        pyo3::exceptions::PyRuntimeError::new_err(format!("component_assignment: {e}"))
    })?;
    let stage = ComponentAssignmentStage {
        slot_spacing,
        fixed_placements,
    };
    let out = stage.run(rust_state).map_err(|e| to_pyerr(&e))?;
    crate::d1_bridge::to_python(py, state.bind(py), &out, &["placements"])
}

#[cfg(feature = "python")]
/// FFI entry for the Python shim's `_assign_components_to_slots`:
/// ``run_component_assignment_kernel(netlist, component_zone_map,
/// zone_slots, fixed_placements, domain_for_ref, domain_regions,
/// slot_spacing)`` -- the leaf orchestration WITHOUT the BoardState guards /
/// frozenset wrap (public-API parity for the shim helper the existing
/// differential drives).
#[pyfunction]
#[allow(clippy::too_many_arguments)]
#[pyo3(signature = (netlist, component_zone_map, zone_slots, fixed_placements, domain_for_ref, domain_regions, slot_spacing))]
pub fn run_component_assignment_kernel(
    py: Python<'_>,
    netlist: Py<PyAny>,
    component_zone_map: Py<PyAny>,
    zone_slots: Py<PyAny>,
    fixed_placements: Py<PyAny>,
    domain_for_ref: Py<PyAny>,
    domain_regions: Py<PyAny>,
    slot_spacing: f64,
) -> PyResult<Py<PyAny>> {
    let result = assign_inner(
        py,
        &netlist,
        component_zone_map.bind(py),
        zone_slots.bind(py),
        &Some(fixed_placements),
        domain_for_ref.bind(py),
        domain_regions.bind(py),
        slot_spacing,
    )?;
    Ok(result.into_any().unbind())
}
