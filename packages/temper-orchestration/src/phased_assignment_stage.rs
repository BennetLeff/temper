// The D5 `PhasedAssignmentStage` of the Rust Orchestration Engine plan
// (2026-08-09-001, Phase D batch D5): a `Stage<BoardState>` implementor
// mirroring the `PhasedComponentAssignmentStage` orchestration that lives in
// the D5 `_phase_*` mixins (`deterministic/stages/_phase_core.py` +
// `_phase_zones.py` + `_phase_rotation.py` + `_phase_validation.py`).
//
// The whole run() orchestration moves to Rust: the identity-preserving state
// guards, the `compiler.validate` warning loop, the U3 design-rules attach,
// `_domain_lookups`, the phase dispatch (`_phased_placement`: template /
// proximity / optimize / unknown-method-warning over
// `constraints.placement_priority`), `_place_template`, `_place_proximity`,
// `_place_optimize` (footprint-size sort, zone lookup with the cross-zone
// fallback, the seed filter call-back, the domain filter, best-slot
// selection), `_simple_greedy_placement`, `_select_best_slot` (the
// slot_filter / slot_scorer / wirelength / routability scoring with
// CPython-`min` first-min-wins semantics), `_reserve_slots` /
// `_reserve_slots_with_hv` (the footprint + HV-creepage ghost-pad rings with
// the nearest-other-HV-pin reduction), and the `frozenset(placements.items())`
// / `frozenset(used_slots)` writes.
//
// The stage reads the config off the Python `PhasedComponentAssignmentStage`
// instance (passed across the FFI as the `stage` argument -- the same
// `__new__`-construction pattern the D4 validator uses): `constraints`,
// `slot_filter`, `slot_scorer`, `design_rules`, `channel_map`, `w_r`,
// `use_isolation_slots`, `_isolation_slots_by_ref`, `seed_filter`,
// `_bottleneck_map`. The `_get_footprint_radius`, `_effective_ghost_pad_radius`
// (design-bundle kernel), `_compute_wirelength` (design-bundle kernel),
// `_apply_bottleneck_filter` (R6 seed-filter logging) and `_is_hv_ref` mixin
// methods are CALLED back on the stage -- single-source, bit-exact by
// construction. shapely `_filter_by_domain` is driven through the shapely
// objects at runtime like the D4 stage. The router_v6 DRC-fence
// (`register_validator` / `run_validators`) call-back stays in the Python
// shim's `run()` (router_v6 surface -- see the D4 note on `StageDRCFailure`).
//
// Bit-exactness notes:
// - `** 2` squares are libm `pow` via `host_math::pow`; `math.sqrt` is
//   `f64::sqrt` (correctly rounded).
// - `max`/`min` are CPython first-arg-wins; the best-slot and nearest-HV-pin
//   `min` scans keep the first element on ties (strict `<`).
// - the footprint-size sort is CPython `sorted` on `(-size, ref)` tuple keys:
//   stable, first element compared with Python `<`-then-`==` semantics
//   (`-0.0`/`0.0` ties and NaN fall through to the ref string, exactly like
//   CPython tuple comparison).
// - dict insertion order is load-bearing (the cross-zone fallback, the
//   cumulative-placement merges, the `net_pins` / `zone_slots` orders) and is
//   reproduced by building the same Python dicts/lists through FFI.

#[cfg(feature = "python")]
use std::borrow::Cow;
#[cfg(feature = "python")]
use std::collections::HashSet;

#[cfg(feature = "python")]
use pyo3::prelude::*;
#[cfg(feature = "python")]
use pyo3::types::{PyDict, PyFloat, PyList, PySet, PyString, PyTuple};

#[cfg(feature = "python")]
use crate::board_state::{BoardState, SlotId};
#[cfg(feature = "python")]
use crate::config_attach_stage::to_pyerr;
#[cfg(feature = "python")]
use crate::derivation_stage::{pyerr_stage, stage_guard};
#[cfg(feature = "python")]
use crate::grid_hv::getattr_default;
#[cfg(feature = "python")]
use crate::host_math;
#[cfg(feature = "python")]
use crate::stage::{Stage, StageError};

#[cfg(feature = "python")]
use temper_data_model::{PlacementSet, StrPairSet, ZoneSlotsSet};

const STAGE_NAME: &str = "phased_component_assignment";
const CORE_LOGGER_NAME: &str = "temper_placer.deterministic.stages._phase_core";

#[cfg(feature = "python")]
/// The phased component-assignment stage: netlist + zone maps + slot grid ->
/// `placements` (frozenset of `(ref, (x, y))`) + `used_slots` (frozenset of
/// grid slots, footprint + HV creepage rings).
///
/// `stage` is the Python `PhasedComponentAssignmentStage` instance -- the
/// config carrier (constraints, compiler, slot filter/scorer, design rules,
/// channel map, mixin helpers). The runner test constructs it with a fake
/// stage object.
#[derive(Debug, Clone)]
pub struct PhasedAssignmentStage {
    pub stage: Py<PyAny>,
}

#[cfg(feature = "python")]
impl Stage<BoardState> for PhasedAssignmentStage {
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
impl PhasedAssignmentStage {
    /// The stage body. The guards return the state unchanged (identity
    /// preserved).
    fn run_inner(&self, py: Python<'_>, state: BoardState) -> PyResult<BoardState> {
        let stage = self.stage.bind(py);

        // `if not state.netlist or not state.component_zone_map or not
        // state.zone_slots: return state`
        let netlist = match &state.netlist {
            Some(n) if n.bind(py).is_truthy()? => n.clone_ref(py),
            _ => return Ok(state),
        };
        // U6 (O-C3) group-2: the guards (`if not state.component_zone_map`)
        // map to `!set.is_empty()`; each owned set is rebuilt into the Python
        // frozenset `dict(...)` expects (the deterministic U5 sorted-repr
        // rebuild — the recorded iteration-order bound).
        let component_zone_map = match &state.component_zone_map {
            Some(c) if !c.is_empty() => crate::marshal::to_python::<StrPairSet>(py, c)?,
            _ => return Ok(state),
        };
        let zone_slots = match &state.zone_slots {
            Some(z) if !z.is_empty() => crate::marshal::to_python::<ZoneSlotsSet>(py, z)?,
            _ => return Ok(state),
        };

        // `errors = self.compiler.validate(state.board, state.netlist)`; each
        // error logs a warning.
        let compiler = stage.getattr("compiler")?;
        let errors = compiler.call_method1("validate", (state.board.clone(), &netlist))?;
        for error in errors.try_iter()? {
            let error = error?;
            let msg = py_format(py, "Constraint validation: {}", &[error.into_any()])?;
            log_msg(py, CORE_LOGGER_NAME, "warning", &msg)?;
        }

        // `if self.design_rules is not None and getattr(state, "design_rules",
        // None) is None: state = replace(state, design_rules=self.design_rules)`
        let mut state = state;
        let stage_dr = stage.getattr("design_rules")?;
        if !stage_dr.is_none() && state.design_rules.is_none() {
            state.design_rules = Some(stage_dr.unbind());
        }

        let (domain_for_ref, domain_regions) = domain_lookups(py, &state)?;

        // `dict(state.component_zone_map)` / `dict(state.zone_slots)` -- the
        // frozensets rebuilt as dicts in frozenset iteration order.
        let czm_dict = builtins_dict(py, component_zone_map.bind(py))?;
        let zs_dict = builtins_dict(py, zone_slots.bind(py))?;

        let (placements, used_slots) = phased_placement(
            py,
            stage,
            netlist.bind(py),
            &czm_dict,
            &zs_dict,
            &domain_for_ref,
            &domain_regions,
        )?;

        // `replace(state, placements=frozenset(placements.items()),
        // used_slots=frozenset(used_slots))`
        let builtins = py.import("builtins")?;
        let items = placements.call_method0("items")?;
        let placements_fs = builtins.getattr("frozenset")?.call1((items,))?;
        let used_slots_fs = builtins.getattr("frozenset")?.call1((&used_slots,))?;
        let mut new_state = state;
        new_state.placements = Some(crate::marshal::to_owned::<PlacementSet>(&placements_fs)?);
        // U1 (O-C3): `frozenset(used_slots)` is still built through CPython
        // (the oracle's exact construction), then marshalled INTO the owned
        // field — the Python placer's slot set is unchanged, only the field's
        // Rust representation is owned now.
        new_state.used_slots = Some(crate::marshal::to_owned::<HashSet<SlotId>>(&used_slots_fs)?);
        Ok(new_state)
    }
}

// ---------------------------------------------------------------------------
// Phase dispatch
// ---------------------------------------------------------------------------

#[cfg(feature = "python")]
/// `_phased_placement`: `comp_by_ref` + `net_pins` + flattened slots, then
/// the placement_priority phase loop. Returns `(placements dict, used_slots
/// set)`.
fn phased_placement<'py>(
    py: Python<'py>,
    stage: &Bound<'py, PyAny>,
    netlist: &Bound<'py, PyAny>,
    component_zone_map: &Bound<'py, PyAny>,
    zone_slots: &Bound<'py, PyAny>,
    domain_for_ref: &Bound<'py, PyDict>,
    domain_regions: &Bound<'py, PyDict>,
) -> PyResult<(Bound<'py, PyDict>, Bound<'py, PySet>)> {
    let placements = PyDict::new(py);
    let used_slots = PySet::empty(py)?;

    let comp_by_ref = PyDict::new(py);
    for comp in netlist.getattr("components")?.try_iter()? {
        let comp = comp?;
        comp_by_ref.set_item(comp.getattr("ref")?, &comp)?;
    }
    let net_pins = build_net_pins(py, netlist)?;
    let all_slots = flatten_slots(py, zone_slots)?;

    let phases = stage.getattr("constraints")?.getattr("placement_priority")?;
    if !phases.is_truthy()? {
        return simple_greedy_placement(py, stage, netlist, component_zone_map, zone_slots);
    }

    let placed_refs = PySet::empty(py)?;
    for (phase_name, phase_config) in dict_items(py, &phases)? {
        let phase_config = phase_config.bind(py);
        let method_raw = phase_config.call_method1("get", ("method", "optimize"))?;
        let method: Option<String> = method_raw.extract()?;

        let mut components: Bound<'py, PyAny> =
            phase_config.call_method1("get", ("components", PyList::empty(py)))?;
        let is_auto = method.as_deref() == Some("auto");
        let has_components = components.len()? > 0;
        if is_auto || !has_components {
            components = PyList::empty(py).into_any();
            for comp in netlist.getattr("components")?.try_iter()? {
                let comp = comp?;
                let ref_val = comp.getattr("ref")?;
                let placed: bool = placed_refs.contains(&ref_val)?;
                if !placed {
                    components.call_method1("append", (ref_val,))?;
                }
            }
        }

        // `[ref for ref in components if ref in comp_by_ref and ref not in
        // placed_refs]`
        let filtered = PyList::empty(py);
        for ref_val in components.try_iter()? {
            let ref_val = ref_val?;
            let in_cbr: bool = comp_by_ref.call_method1("__contains__", (&ref_val,))?.extract()?;
            let placed: bool = placed_refs.contains(&ref_val)?;
            if in_cbr && !placed {
                filtered.append(ref_val)?;
            }
        }
        let components = filtered;
        if components.len() == 0 {
            continue;
        }

        let phase_placements = match method.as_deref() {
            Some("template") => place_template(
                py, stage, &components, phase_config, &comp_by_ref, &all_slots,
                &used_slots, &placements, netlist,
            )?,
            Some("proximity") => place_proximity(
                py, stage, &components, phase_config, &comp_by_ref, &placements,
                zone_slots, &used_slots, &all_slots, &net_pins, netlist,
            )?,
            Some("optimize") | Some("auto") => place_optimize(
                py, stage, &components, &comp_by_ref, component_zone_map, zone_slots,
                &placements, &used_slots, &all_slots, &net_pins, Some(netlist),
                domain_for_ref, domain_regions,
            )?,
            _ => {
                let method_name = method.as_deref().unwrap_or("None");
                let msg = py_format(
                    py,
                    "Unknown placement method '{}' in phase '{}'",
                    &[
                        PyString::new(py, method_name).into_any(),
                        phase_name.bind(py).clone().into_any(),
                    ],
                )?;
                log_msg(py, CORE_LOGGER_NAME, "warning", &msg)?;
                continue;
            }
        };

        // `placements.update(phase_placements)` /
        // `placed_refs.update(phase_placements.keys())`
        for (k, v) in dict_items(py, &phase_placements)? {
            placements.set_item(&k, &v)?;
            placed_refs.add(k)?;
        }
    }

    Ok((placements, used_slots))
}

#[cfg(feature = "python")]
/// `_build_net_pins`: `net.name -> list(net.pins)` in netlist order.
fn build_net_pins<'py>(
    py: Python<'py>,
    netlist: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyDict>> {
    let net_pins = PyDict::new(py);
    let builtins = py.import("builtins")?;
    for net in netlist.getattr("nets")?.try_iter()? {
        let net = net?;
        let pins = net.getattr("pins")?;
        net_pins.set_item(net.getattr("name")?, builtins.getattr("list")?.call1((pins,))?)?;
    }
    Ok(net_pins)
}

#[cfg(feature = "python")]
/// `_flatten_slots`: every zone's slot list in zone-dict order.
fn flatten_slots<'py>(
    py: Python<'py>,
    zone_slots: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyList>> {
    let all = PyList::empty(py);
    for slots in zone_slots.call_method0("values")?.try_iter()? {
        all.call_method1("extend", (slots?,))?;
    }
    Ok(all)
}

#[cfg(feature = "python")]
/// `_domain_lookups`: the per-ref domain dict + the HV_edge / LV_interior
/// region dict from `state.domain_regions`.
fn domain_lookups<'py>(
    py: Python<'py>,
    state: &BoardState,
) -> PyResult<(Bound<'py, PyDict>, Bound<'py, PyDict>)> {
    let domain_for_ref = PyDict::new(py);
    let domain_regions = PyDict::new(py);
    let domain_map = match &state.component_domain_map {
        Some(d) if d.bind(py).is_truthy()? => d.bind(py),
        _ => return Ok((domain_for_ref, domain_regions)),
    };
    let regions = match &state.domain_regions {
        Some(r) if r.bind(py).is_truthy()? => r.bind(py),
        _ => return Ok((domain_for_ref, domain_regions)),
    };
    for pair in domain_map.try_iter()? {
        let pair = pair?;
        domain_for_ref.set_item(pair.get_item(0)?, pair.get_item(1)?)?;
    }
    let n_regions = regions.len()?;
    if n_regions >= 2 {
        domain_regions.set_item("HV_edge", regions.get_item(0)?)?;
        domain_regions.set_item("LV_interior", regions.get_item(1)?)?;
    } else if n_regions == 1 {
        domain_regions.set_item("LV_interior", regions.get_item(0)?)?;
    }
    Ok((domain_for_ref, domain_regions))
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

// ---------------------------------------------------------------------------
// Placement methods
// ---------------------------------------------------------------------------

#[cfg(feature = "python")]
/// `_place_template`: anchor + `i * 10.0` offsets, footprint+HV reservation.
#[allow(clippy::too_many_arguments)]
fn place_template<'py>(
    py: Python<'py>,
    stage: &Bound<'py, PyAny>,
    components: &Bound<'py, PyList>,
    phase_config: &Bound<'py, PyAny>,
    comp_by_ref: &Bound<'py, PyDict>,
    all_slots: &Bound<'py, PyList>,
    used_slots: &Bound<'py, PySet>,
    current_placements: &Bound<'py, PyDict>,
    netlist: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyDict>> {
    let anchor = phase_config.call_method1("get", ("anchor", PyList::new(py, [0i64, 0i64])?))?;
    let ax: f64 = anchor.get_item(0)?.extract()?;
    let ay: f64 = anchor.get_item(1)?.extract()?;

    let placements = PyDict::new(py);
    for (i, ref_val) in components.try_iter()?.enumerate() {
        let ref_val = ref_val?;
        let in_cbr: bool = comp_by_ref.call_method1("__contains__", (&ref_val,))?.extract()?;
        if !in_cbr {
            continue;
        }
        let offset_y = i as f64 * 10.0;
        let pos = PyTuple::new(py, [PyFloat::new(py, ax), PyFloat::new(py, ay + offset_y)])?;
        placements.set_item(&ref_val, &pos)?;
        let cumulative = merge_dicts(py, current_placements, &placements)?;
        let component = comp_by_ref.call_method1("__getitem__", (&ref_val,))?;
        reserve_slots_with_hv(py, stage, &component, &pos, all_slots, used_slots, &cumulative, Some(netlist))?;
    }
    Ok(placements)
}

#[cfg(feature = "python")]
/// `_place_proximity`: slots within `max_distance_mm` of the reference's
/// position, best-slot selected; the missing-reference / missing-placement
/// fallback delegates to `_place_optimize` WITHOUT netlist or domain args.
#[allow(clippy::too_many_arguments)]
fn place_proximity<'py>(
    py: Python<'py>,
    stage: &Bound<'py, PyAny>,
    components: &Bound<'py, PyList>,
    phase_config: &Bound<'py, PyAny>,
    comp_by_ref: &Bound<'py, PyDict>,
    current_placements: &Bound<'py, PyDict>,
    zone_slots: &Bound<'py, PyAny>,
    used_slots: &Bound<'py, PySet>,
    all_slots: &Bound<'py, PyList>,
    net_pins: &Bound<'py, PyDict>,
    netlist: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyDict>> {
    let reference_ref = phase_config.call_method1("get", ("reference",))?;
    let max_distance_mm: f64 = phase_config
        .call_method1("get", ("max_distance_mm", 20.0))?
        .extract()?;

    let reference_missing = reference_ref.is_none()
        || !current_placements
            .call_method1("__contains__", (&reference_ref,))?
            .extract::<bool>()?;

    let empty_map = PyDict::new(py);
    let empty_domains = PyDict::new(py);
    if reference_missing {
        // `_place_optimize(components, comp_by_ref, {}, zone_slots,
        // current_placements, used_slots, all_slots, net_pins)` -- no
        // netlist, no domains (full base-radius HV rings).
        return place_optimize(
            py, stage, components, comp_by_ref, &empty_map.into_any(), zone_slots,
            current_placements, used_slots, all_slots, net_pins, None,
            &empty_domains, &empty_domains,
        );
    }

    let placements = PyDict::new(py);
    let reference_pos = match current_placements.get_item(&reference_ref)? {
        Some(p) => p,
        // unreachable: `reference_missing` guards `__contains__`
        None => return Ok(placements),
    };

    for ref_val in components.try_iter()? {
        let ref_val = ref_val?;
        let in_cbr: bool = comp_by_ref.call_method1("__contains__", (&ref_val,))?.extract()?;
        if !in_cbr {
            continue;
        }
        let component = comp_by_ref.call_method1("__getitem__", (&ref_val,))?;

        let all_zone_slots = PyList::empty(py);
        for slots in zone_slots.call_method0("values")?.try_iter()? {
            all_zone_slots.call_method1("extend", (slots?,))?;
        }

        let nearby_slots = PyList::empty(py);
        for slot in all_zone_slots.try_iter()? {
            let slot = slot?;
            let used: bool = used_slots.contains(&slot)?;
            let dist = distance(py, &slot, &reference_pos)?;
            if !used && dist <= max_distance_mm {
                nearby_slots.append(slot)?;
            }
        }
        if nearby_slots.len() == 0 {
            continue;
        }

        let best_slot = select_best_slot(
            py, stage, &ref_val, &nearby_slots, current_placements.as_any(), placements.as_any(), net_pins.as_any(),
        )?;
        if !best_slot.is_none() {
            placements.set_item(&ref_val, &best_slot)?;
            let cumulative = merge_dicts(py, current_placements, &placements)?;
            reserve_slots_with_hv(py, stage, &component, &best_slot, all_slots, used_slots, &cumulative, Some(netlist))?;
        }
    }
    Ok(placements)
}

#[cfg(feature = "python")]
/// `_place_optimize`: footprint-size sort (largest first), zone slot list
/// with the cross-zone fallback, seed-filter call-back, domain filter,
/// best-slot selection and footprint+HV reservation.
#[allow(clippy::too_many_arguments)]
fn place_optimize<'py>(
    py: Python<'py>,
    stage: &Bound<'py, PyAny>,
    components: &Bound<'py, PyList>,
    comp_by_ref: &Bound<'py, PyDict>,
    component_zone_map: &Bound<'py, PyAny>,
    zone_slots: &Bound<'py, PyAny>,
    current_placements: &Bound<'py, PyDict>,
    used_slots: &Bound<'py, PySet>,
    all_slots: &Bound<'py, PyList>,
    net_pins: &Bound<'py, PyDict>,
    netlist: Option<&Bound<'py, PyAny>>,
    domain_for_ref: &Bound<'py, PyDict>,
    domain_regions: &Bound<'py, PyDict>,
) -> PyResult<Bound<'py, PyDict>> {
    let placements = PyDict::new(py);

    // `sorted(components, key=lambda r: (-get_size(r), r))`
    let mut items: Vec<(f64, String, Bound<'py, PyAny>)> = Vec::new();
    for ref_val in components.try_iter()? {
        let ref_val = ref_val?;
        let ref_name: String = ref_val.extract()?;
        let size = get_size(py, &ref_val, comp_by_ref)?;
        items.push((-size, ref_name, ref_val));
    }
    items.sort_by(|a, b| py_tuple_key_cmp(&a.0, &a.1, &b.0, &b.1));

    let builtins = py.import("builtins")?;
    for (_key, _, ref_val) in items {
        let in_cbr: bool = comp_by_ref.call_method1("__contains__", (&ref_val,))?.extract()?;
        if !in_cbr {
            continue;
        }
        let component = comp_by_ref.call_method1("__getitem__", (&ref_val,))?;

        let zone_name = component_zone_map.call_method1("get", (&ref_val, "Signal"))?;
        let zone_slot_list = builtins
            .getattr("list")?
            .call1((zone_slots.call_method1("get", (&zone_name, PyTuple::empty(py)))?,))?;

        let mut available_slots = PyList::empty(py);
        for s in zone_slot_list.try_iter()? {
            let s = s?;
            let used: bool = used_slots.contains(&s)?;
            if !used {
                available_slots.append(s)?;
            }
        }
        if available_slots.len() == 0 {
            for slots in zone_slots.call_method0("values")?.try_iter()? {
                let slots = slots?;
                let cand = PyList::empty(py);
                for s in slots.try_iter()? {
                    let s = s?;
                    let used: bool = used_slots.contains(&s)?;
                    if !used {
                        cand.append(s)?;
                    }
                }
                if cand.len() > 0 {
                    available_slots = cand;
                    break;
                }
            }
        }
        if available_slots.len() == 0 {
            continue;
        }

        let filtered = stage.call_method1("_apply_bottleneck_filter", (&ref_val, &available_slots, comp_by_ref))?;
        if filtered.len()? == 0 {
            continue;
        }

        let domain_filtered = filter_by_domain(py, &ref_val, &filtered, domain_for_ref, domain_regions)?;
        if domain_filtered.len() == 0 {
            continue;
        }

        let best_slot = select_best_slot(
            py, stage, &ref_val, &domain_filtered, current_placements.as_any(), placements.as_any(), net_pins.as_any(),
        )?;
        if !best_slot.is_none() {
            placements.set_item(&ref_val, &best_slot)?;
            let cumulative = merge_dicts(py, current_placements, &placements)?;
            reserve_slots_with_hv(py, stage, &component, &best_slot, all_slots, used_slots, &cumulative, netlist)?;
        }
    }
    Ok(placements)
}

#[cfg(feature = "python")]
/// `_filter_by_domain`: keep the slots whose slot-point the component's
/// domain region covers (shapely driven through FFI).
fn filter_by_domain<'py>(
    py: Python<'py>,
    ref_val: &Bound<'py, PyAny>,
    slots: &Bound<'py, PyAny>,
    domain_for_ref: &Bound<'py, PyDict>,
    domain_regions: &Bound<'py, PyDict>,
) -> PyResult<Bound<'py, PyList>> {
    if domain_for_ref.len() == 0 || domain_regions.len() == 0 {
        let out = PyList::empty(py);
        for s in slots.try_iter()? {
            out.append(s?)?;
        }
        return Ok(out);
    }
    let domain = domain_for_ref.call_method1("get", (ref_val,))?;
    if domain.is_none() || !domain.is_truthy()? {
        let out = PyList::empty(py);
        for s in slots.try_iter()? {
            out.append(s?)?;
        }
        return Ok(out);
    }
    let region = domain_regions.call_method1("get", (&domain,))?;
    if region.is_none() {
        let out = PyList::empty(py);
        for s in slots.try_iter()? {
            out.append(s?)?;
        }
        return Ok(out);
    }
    let is_empty: bool = region.getattr("is_empty")?.extract()?;
    if is_empty {
        let out = PyList::empty(py);
        for s in slots.try_iter()? {
            out.append(s?)?;
        }
        return Ok(out);
    }
    let point_cls = py.import("shapely.geometry")?.getattr("Point")?;
    let out = PyList::empty(py);
    for s in slots.try_iter()? {
        let s = s?;
        let p = point_cls.call1((s.get_item(0)?, s.get_item(1)?))?;
        let covers: bool = region.call_method1("covers", (p,))?.extract()?;
        if covers {
            out.append(s)?;
        }
    }
    Ok(out)
}

#[cfg(feature = "python")]
/// `_select_best_slot` (shared by the Rust run and the `_select_best_slot`
/// shim delegation): slot_filter + slot_scorer + wirelength + routability
/// scoring with CPython `min` first-minimum-wins semantics.
fn select_best_slot<'py>(
    py: Python<'py>,
    stage: &Bound<'py, PyAny>,
    component_ref: &Bound<'py, PyAny>,
    candidate_slots: &Bound<'py, PyAny>,
    current_placements: &Bound<'py, PyAny>,
    phase_placements: &Bound<'py, PyAny>,
    net_pins: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let all_placements = merge_dicts(py, current_placements, phase_placements)?;
    let slot_filter = stage.getattr("slot_filter")?;
    let slot_scorer = stage.getattr("slot_scorer")?;
    let w_r: f64 = stage.getattr("w_r")?.extract()?;
    let channel_map = stage.getattr("channel_map")?;

    let valid_slots = PyList::empty(py);
    for slot in candidate_slots.try_iter()? {
        let slot = slot?;
        let ok: bool = slot_filter
            .call1((&slot, component_ref, &all_placements))?
            .is_truthy()?;
        if ok {
            valid_slots.append(slot)?;
        }
    }
    if valid_slots.len() == 0 {
        for s in candidate_slots.try_iter()? {
            valid_slots.append(s?)?;
        }
    }

    let routability_penalty = py
        .import("temper_placer.deterministic.channels")?
        .getattr("routability_penalty")?;

    let mut best: Option<Bound<'py, PyAny>> = None;
    let mut best_score = 0.0f64;
    for slot in valid_slots.try_iter()? {
        let slot = slot?;
        let constraint_penalty: f64 = slot_scorer
            .call1((&slot, component_ref, &all_placements))?
            .extract()?;
        let wirelength: f64 = stage
            .call_method1("_compute_wirelength", (component_ref, &slot, net_pins, &all_placements))?
            .extract()?;
        let routability = if !channel_map.is_none() && w_r > 0.0 {
            let p: f64 = routability_penalty.call1((&slot, &channel_map))?.extract()?;
            p * w_r
        } else {
            0.0
        };
        let score = constraint_penalty + wirelength * 0.1 + routability;
        match &best {
            None => {
                best_score = score;
                best = Some(slot.clone());
            }
            Some(_) => {
                if score < best_score {
                    best_score = score;
                    best = Some(slot.clone());
                }
            }
        }
    }
    Ok(match best {
        Some(b) => b,
        None => py.None().bind(py).clone(),
    })
}

#[cfg(feature = "python")]
/// `_simple_greedy_placement`: the no-phases fallback (wirelength-only,
/// no HV rings).
fn simple_greedy_placement<'py>(
    py: Python<'py>,
    stage: &Bound<'py, PyAny>,
    netlist: &Bound<'py, PyAny>,
    component_zone_map: &Bound<'py, PyAny>,
    zone_slots: &Bound<'py, PyAny>,
) -> PyResult<(Bound<'py, PyDict>, Bound<'py, PySet>)> {
    let placements = PyDict::new(py);
    let used_slots = PySet::empty(py)?;
    let net_pins = build_net_pins(py, netlist)?;
    let all_slots = flatten_slots(py, zone_slots)?;
    let builtins = py.import("builtins")?;

    let mut items: Vec<(f64, String, Bound<'py, PyAny>)> = Vec::new();
    for component in netlist.getattr("components")?.try_iter()? {
        let component = component?;
        let ref_name: String = component.getattr("ref")?.extract()?;
        let size = get_size_of(py, &component)?;
        items.push((-size, ref_name.clone(), component));
    }
    items.sort_by(|a, b| py_tuple_key_cmp(&a.0, &a.1, &b.0, &b.1));

    for (_key, _, component) in items {
        let ref_val = component.getattr("ref")?;
        let zone_name = component_zone_map.call_method1("get", (&ref_val, "Signal"))?;
        let zone_slot_list = builtins.getattr("list")?.call1((
            zone_slots.call_method1("get", (&zone_name, PyTuple::empty(py)))?,
        ))?;
        let available = PyList::empty(py);
        for s in zone_slot_list.try_iter()? {
            let s = s?;
            let used: bool = used_slots.contains(&s)?;
            if !used {
                available.append(s)?;
            }
        }
        if available.len() == 0 {
            continue;
        }

        // `min(available, key=lambda s: self._compute_wirelength(ref, s,
        // net_pins, placements))` -- first-minimum-wins.
        let mut best: Option<Bound<'py, PyAny>> = None;
        let mut best_score = 0.0f64;
        for s in available.try_iter()? {
            let s = s?;
            let wl: f64 = stage
                .call_method1("_compute_wirelength", (&ref_val, &s, &net_pins, &placements))?
                .extract()?;
            match &best {
                None => {
                    best_score = wl;
                    best = Some(s.clone());
                }
                Some(_) => {
                    if wl < best_score {
                        best_score = wl;
                        best = Some(s.clone());
                    }
                }
            }
        }
        if let Some(best_slot) = best {
            placements.set_item(&ref_val, &best_slot)?;
            let radius: f64 = stage.call_method1("_get_footprint_radius", (&component,))?.extract()?;
            reserve_slots(&best_slot, radius, &all_slots, &used_slots)?;
        }
    }
    Ok((placements, used_slots))
}

// ---------------------------------------------------------------------------
// HV creepage / slot reservation
// ---------------------------------------------------------------------------

#[cfg(feature = "python")]
/// `_reserve_slots_with_hv`: the footprint ring, then the HV creepage rings
/// (base radius from the HV/AC net classes, per-pin absolute positions, the
/// nearest-other-HV-pin reduction through `_effective_ghost_pad_radius`).
#[allow(clippy::too_many_arguments)]
fn reserve_slots_with_hv<'py>(
    py: Python<'py>,
    stage: &Bound<'py, PyAny>,
    component: &Bound<'py, PyAny>,
    placed_pos: &Bound<'py, PyAny>,
    all_slots: &Bound<'py, PyList>,
    used_slots: &Bound<'py, PySet>,
    placements: &Bound<'py, PyDict>,
    netlist: Option<&Bound<'py, PyAny>>,
) -> PyResult<()> {
    let radius: f64 = stage.call_method1("_get_footprint_radius", (component,))?.extract()?;
    reserve_slots(placed_pos, radius, all_slots, used_slots)?;

    let design_rules = stage.getattr("design_rules")?;
    if design_rules.is_none() {
        return Ok(());
    }
    let pins = component.getattr("pins")?;
    if pins.is_none() {
        return Ok(());
    }

    // `base_radius = max over the HV/AC net classes of creepage_mm`.
    let net_classes = design_rules.getattr("net_classes")?;
    let net_class_assignments = design_rules.getattr("net_class_assignments")?;
    let mut base_radius = 0.0f64;
    for rules in net_classes.call_method0("values")?.try_iter()? {
        let rules = rules?;
        let safety = rules.getattr("safety_category")?;
        if is_hv_safety(&safety)? {
            let creep: f64 = getattr_default(py, &rules, "creepage_mm", PyFloat::new(py, 0.0).into_any().unbind())?
                .extract()?;
            base_radius = py_max(base_radius, creep);
        }
    }
    if base_radius <= 0.0 {
        return Ok(());
    }

    // `other_hv_pins`: absolute positions of every HV pin on a DIFFERENT
    // already-placed component (in placements-dict order).
    let mut other_hv_pins: Vec<(f64, f64)> = Vec::new();
    if let Some(nl) = netlist {
        let comp_ref = component.getattr("ref")?;
        for (other_ref, other_pos) in dict_items(py, placements)? {
            let same: bool = other_ref.bind(py).eq(&comp_ref)?;
            if same {
                continue;
            }
            let other_comp = match find_by_ref(py, nl, other_ref.bind(py))? {
                Some(c) => c,
                None => continue,
            };
            let other_pins = other_comp.getattr("pins")?;
            if other_pins.is_none() {
                continue;
            }
            let ox: f64 = other_pos.bind(py).get_item(0)?.extract()?;
            let oy: f64 = other_pos.bind(py).get_item(1)?.extract()?;
            for op in other_pins.try_iter()? {
                let op = op?;
                let op_net = op.getattr("net")?;
                if op_net.is_none() {
                    continue;
                }
                let other_class = net_class_assignments.call_method1("get", (&op_net,))?;
                if other_class.is_none() {
                    continue;
                }
                let in_nc: bool = net_classes.call_method1("__contains__", (&other_class,))?.extract()?;
                if !in_nc {
                    continue;
                }
                let other_entry = net_classes.call_method1("__getitem__", (&other_class,))?;
                let other_safety = other_entry.getattr("safety_category")?;
                if !is_hv_safety(&other_safety)? {
                    continue;
                }
                let op_pos = op.getattr("position")?;
                let opx: f64 = op_pos.get_item(0)?.extract()?;
                let opy: f64 = op_pos.get_item(1)?.extract()?;
                other_hv_pins.push((ox + opx, oy + opy));
            }
        }
    }

    let cx: f64 = placed_pos.get_item(0)?.extract()?;
    let cy: f64 = placed_pos.get_item(1)?.extract()?;
    for pin in pins.try_iter()? {
        let pin = pin?;
        let pin_net = pin.getattr("net")?;
        if pin_net.is_none() {
            continue;
        }
        let class_name = net_class_assignments.call_method1("get", (&pin_net,))?;
        if class_name.is_none() {
            continue;
        }
        let in_nc: bool = net_classes.call_method1("__contains__", (&class_name,))?.extract()?;
        if !in_nc {
            continue;
        }
        let class_entry = net_classes.call_method1("__getitem__", (&class_name,))?;
        let safety = class_entry.getattr("safety_category")?;
        if !is_hv_safety(&safety)? {
            continue;
        }
        let pin_pos = pin.getattr("position")?;
        let px: f64 = pin_pos.get_item(0)?.extract()?;
        let py_: f64 = pin_pos.get_item(1)?.extract()?;
        let abs_x = cx + px;
        let abs_y = cy + py_;

        let mut nearest_other = (0.0, 0.0);
        if !other_hv_pins.is_empty() {
            let mut best_d = f64::INFINITY;
            for &(x2, y2) in &other_hv_pins {
                let d = host_math::pow(x2 - abs_x, 2.0) + host_math::pow(y2 - abs_y, 2.0);
                if d < best_d {
                    best_d = d;
                    nearest_other = (x2, y2);
                }
            }
        }

        let ring_radius: f64 = stage
            .call_method1(
                "_effective_ghost_pad_radius",
                (
                    component.getattr("ref")?,
                    pin.getattr("name")?,
                    PyFloat::new(py, base_radius),
                    PyTuple::new(py, [abs_x, abs_y])?,
                    PyTuple::new(py, [nearest_other.0, nearest_other.1])?,
                ),
            )?
            .extract()?;
        if ring_radius <= 0.0 {
            continue;
        }
        let center = PyTuple::new(py, [abs_x, abs_y])?;
        reserve_slots(&center, ring_radius, all_slots, used_slots)?;
    }
    Ok(())
}

#[cfg(feature = "python")]
/// `_reserve_slots`: `math.sqrt((sx - cx) ** 2 + (sy - cy) ** 2) <= radius`
/// over every slot, added to the used set.
fn reserve_slots<'py>(
    center: &Bound<'py, PyAny>,
    radius: f64,
    all_slots: &Bound<'py, PyList>,
    used_slots: &Bound<'py, PySet>,
) -> PyResult<()> {
    let cx: f64 = center.get_item(0)?.extract()?;
    let cy: f64 = center.get_item(1)?.extract()?;
    for slot in all_slots.try_iter()? {
        let slot = slot?;
        let sx: f64 = slot.get_item(0)?.extract()?;
        let sy: f64 = slot.get_item(1)?.extract()?;
        let dist = f64::sqrt(host_math::pow(sx - cx, 2.0) + host_math::pow(sy - cy, 2.0));
        if dist <= radius {
            used_slots.add(slot)?;
        }
    }
    Ok(())
}

#[cfg(feature = "python")]
/// `_distance`: `math.sqrt((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2)`.
fn distance<'py>(
    _py: Python<'py>,
    p1: &Bound<'py, PyAny>,
    p2: &Bound<'py, PyAny>,
) -> PyResult<f64> {
    let x1: f64 = p1.get_item(0)?.extract()?;
    let y1: f64 = p1.get_item(1)?.extract()?;
    let x2: f64 = p2.get_item(0)?.extract()?;
    let y2: f64 = p2.get_item(1)?.extract()?;
    Ok(f64::sqrt(host_math::pow(x1 - x2, 2.0) + host_math::pow(y1 - y2, 2.0)))
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

#[cfg(feature = "python")]
/// `max(comp.bounds)` for a ref-resolved component (or 0).
fn get_size<'py>(
    py: Python<'py>,
    ref_val: &Bound<'py, PyAny>,
    comp_by_ref: &Bound<'py, PyDict>,
) -> PyResult<f64> {
    let comp = comp_by_ref.call_method1("get", (ref_val,))?;
    if comp.is_none() {
        return Ok(0.0);
    }
    get_size_of(py, &comp)
}

#[cfg(feature = "python")]
/// `max(comp.bounds)` (or 0) for a component object.
fn get_size_of<'py>(py: Python<'py>, comp: &Bound<'py, PyAny>) -> PyResult<f64> {
    if !comp.hasattr("bounds")? {
        return Ok(0.0);
    }
    let bounds = comp.getattr("bounds")?;
    if !bounds.is_truthy()? {
        return Ok(0.0);
    }
    let m = py.import("builtins")?.getattr("max")?.call1((bounds,))?;
    m.extract()
}

/// CPython `sorted` tuple-key comparison on `(-size, ref)`: `<` on the float,
/// ties/`-0.0`/NaN fall through to the ref string exactly like CPython tuple
/// comparison.
fn py_tuple_key_cmp(a: &f64, a_ref: &str, b: &f64, b_ref: &str) -> std::cmp::Ordering {
    match a.partial_cmp(b) {
        Some(std::cmp::Ordering::Equal) => a_ref.cmp(b_ref),
        Some(o) => o,
        None => std::cmp::Ordering::Equal,
    }
}

#[cfg(feature = "python")]
/// `next((c for c in netlist.components if c.ref == ref), None)`.
fn find_by_ref<'py>(
    py: Python<'py>,
    netlist: &Bound<'py, PyAny>,
    ref_val: &Bound<'py, PyAny>,
) -> PyResult<Option<Bound<'py, PyAny>>> {
    for component in netlist.getattr("components")?.try_iter()? {
        let component = component?;
        let same: bool = component.getattr("ref")?.eq(ref_val)?;
        if same {
            return Ok(Some(component));
        }
    }
    let _ = py;
    Ok(None)
}

#[cfg(feature = "python")]
/// `{**a, **b}` -- dict merge in a-then-b order (insertion order is
/// load-bearing for the cumulative placement views).
fn merge_dicts<'py>(
    py: Python<'py>,
    a: &Bound<'py, PyAny>,
    b: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyDict>> {
    let out = PyDict::new(py);
    for (k, v) in dict_items(py, a)? {
        out.set_item(&k, &v)?;
    }
    for (k, v) in dict_items(py, b)? {
        out.set_item(&k, &v)?;
    }
    Ok(out)
}

#[cfg(feature = "python")]
/// The HV/AC safety categories (the `_HV_SAFETY_CATEGORIES` set membership).
fn is_hv_safety(safety: &Bound<'_, PyAny>) -> PyResult<bool> {
    if safety.is_none() {
        return Ok(false);
    }
    let s: String = safety.extract()?;
    Ok(s == "HV" || s == "AC")
}

/// CPython `max(a, b)`: first-arg-wins on ties/NaN.
fn py_max(a: f64, b: f64) -> f64 {
    if b > a {
        b
    } else {
        a
    }
}

#[cfg(feature = "python")]
/// CPython `str.format(template, *args)`.
fn py_format<'py>(
    py: Python<'py>,
    template: &str,
    args: &[Bound<'py, PyAny>],
) -> PyResult<Bound<'py, PyAny>> {
    let s = PyString::new(py, template);
    s.call_method1("format", PyTuple::new(py, args)?)
}

#[cfg(feature = "python")]
/// `logging.getLogger(name).<level>(message)`.
fn log_msg(py: Python<'_>, logger_name: &str, level: &str, msg: &Bound<'_, PyAny>) -> PyResult<()> {
    let logger = py.import("logging")?.call_method1("getLogger", (logger_name,))?;
    logger.call_method1(level, (msg,))?;
    Ok(())
}

#[cfg(feature = "python")]
/// A dict's `items()` in insertion order.
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
/// FFI entry for the Python shim: `run_phased_assignment(state, stage)` --
/// `stage` is the Python `PhasedComponentAssignmentStage` instance (the
/// config carrier).
#[pyfunction]
#[pyo3(signature = (state, stage))]
pub fn run_phased_assignment(
    py: Python<'_>,
    state: Py<PyAny>,
    stage: Py<PyAny>,
) -> PyResult<Py<PyAny>> {
    let rust_state = crate::d1_bridge::from_python(py, state.bind(py)).map_err(|e| {
        pyo3::exceptions::PyRuntimeError::new_err(format!("{STAGE_NAME}: {e}"))
    })?;
    let rust_stage = PhasedAssignmentStage { stage };
    let out = rust_stage.run(rust_state).map_err(|e| to_pyerr(&e))?;
    crate::d1_bridge::to_python(
        py,
        state.bind(py),
        &out,
        &["design_rules", "placements", "used_slots"],
    )
}

#[cfg(feature = "python")]
/// FFI entry for the Python shim's `_select_best_slot`:
/// `run_phase_select_best_slot(stage, component_ref, candidate_slots,
/// current_placements, phase_placements, net_pins)` -- the scoring kernel
/// without the BoardState machinery (public-API parity for the shim helper
/// the channel-integration tests drive).
#[pyfunction]
#[allow(clippy::too_many_arguments)]
#[pyo3(signature = (stage, component_ref, candidate_slots, current_placements, phase_placements, net_pins))]
pub fn run_phase_select_best_slot(
    py: Python<'_>,
    stage: Py<PyAny>,
    component_ref: Py<PyAny>,
    candidate_slots: Py<PyAny>,
    current_placements: Py<PyAny>,
    phase_placements: Py<PyAny>,
    net_pins: Py<PyAny>,
) -> PyResult<Py<PyAny>> {
    let stage_bound = stage.bind(py);
    let result = select_best_slot(
        py,
        stage_bound,
        component_ref.bind(py),
        candidate_slots.bind(py),
        current_placements.bind(py),
        phase_placements.bind(py),
        net_pins.bind(py),
    )?;
    Ok(result.unbind())
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

    // -- py_max ------------------------------------------------------------

    #[cfg_attr(test, test)]
    fn py_max_nan_first_argument_wins() {
        assert!(py_max(f64::NAN, 1.0).is_nan());
        assert_eq!(py_max(1.0, f64::NAN), 1.0);
        assert!(py_max(f64::NAN, f64::NAN).is_nan());
    }

    #[cfg_attr(test, test)]
    fn py_max_ties_keep_first() {
        assert_eq!(py_max(0.0, -0.0), 0.0);
        let r = py_max(-0.0, 0.0);
        assert_eq!(r.to_bits(), (-0.0f64).to_bits(),
            "py_max(-0.0, 0.0) must return -0.0, got {r}");
        assert_eq!(py_max(3.0, 3.0), 3.0);
    }

    #[cfg_attr(test, test)]
    fn py_max_infinity() {
        assert_eq!(py_max(f64::INFINITY, 0.0), f64::INFINITY);
        assert_eq!(py_max(0.0, f64::INFINITY), f64::INFINITY);
        assert_eq!(py_max(f64::NEG_INFINITY, 0.0), 0.0);
        assert!(py_max(f64::NAN, f64::NEG_INFINITY).is_nan());
    }

    // -- py_tuple_key_cmp --------------------------------------------------

    #[cfg_attr(test, test)]
    fn tuple_cmp_normal_floats() {
        // Larger negative (more negative) = smaller
        assert_eq!(py_tuple_key_cmp(&-5.0, "A", &-3.0, "B"), std::cmp::Ordering::Less);
        assert_eq!(py_tuple_key_cmp(&-3.0, "A", &-5.0, "B"), std::cmp::Ordering::Greater);
        // Equal floats fall through to string comparison
        assert_eq!(py_tuple_key_cmp(&-3.0, "A", &-3.0, "B"), std::cmp::Ordering::Less);
        assert_eq!(py_tuple_key_cmp(&-3.0, "B", &-3.0, "A"), std::cmp::Ordering::Greater);
        assert_eq!(py_tuple_key_cmp(&-3.0, "A", &-3.0, "A"), std::cmp::Ordering::Equal);
    }

    #[cfg_attr(test, test)]
    fn tuple_cmp_nan_falls_through_to_ref() {
        // CPython NaN-vs-normal: both < are False, == is False -> returns
        // False without checking remaining elements. In a stable sort, this
        // is equivalent to Equal (original order preserved). Our fn returns
        // Equal for all NaN comparisons (the conservative choice).
        assert_eq!(
            py_tuple_key_cmp(&f64::NAN, "A", &5.0, "B"),
            std::cmp::Ordering::Equal
        );
        assert_eq!(
            py_tuple_key_cmp(&f64::NAN, "B", &5.0, "A"),
            std::cmp::Ordering::Equal
        );
        // NaN vs NaN: CPython falls through to ref if the SAME object,
        // returns False (equal for sort) if different objects. We can't
        // distinguish, so Equal is the conservative choice.
        assert_eq!(
            py_tuple_key_cmp(&f64::NAN, "A", &f64::NAN, "B"),
            std::cmp::Ordering::Equal
        );
        assert_eq!(
            py_tuple_key_cmp(&f64::NAN, "A", &f64::NAN, "A"),
            std::cmp::Ordering::Equal
        );
    }

    #[cfg_attr(test, test)]
    fn tuple_cmp_negative_zero_vs_zero() {
        // -0.0 and 0.0 are equal in partial_cmp -> fall through to ref
        // First element ties, string comparison decides.
        assert_eq!(
            py_tuple_key_cmp(&-0.0, "A", &0.0, "B"),
            std::cmp::Ordering::Less
        );
        assert_eq!(
            py_tuple_key_cmp(&0.0, "B", &-0.0, "A"),
            std::cmp::Ordering::Greater
        );
        // Both -0.0 or both 0.0 -> equal
        assert_eq!(
            py_tuple_key_cmp(&-0.0, "X", &-0.0, "X"),
            std::cmp::Ordering::Equal
        );
        assert_eq!(
            py_tuple_key_cmp(&0.0, "X", &0.0, "X"),
            std::cmp::Ordering::Equal
        );
    }

    #[cfg_attr(test, test)]
    fn tuple_cmp_infinity() {
        assert_eq!(py_tuple_key_cmp(&f64::INFINITY, "A", &1.0, "B"), std::cmp::Ordering::Greater);
        assert_eq!(py_tuple_key_cmp(&f64::NEG_INFINITY, "A", &1.0, "B"), std::cmp::Ordering::Less);
        assert_eq!(py_tuple_key_cmp(&f64::INFINITY, "A", &f64::INFINITY, "B"), std::cmp::Ordering::Less);
    }

    // -----------------------------------------------------------------------
    // Deterministic mirrors of `proptests`' six properties (P1-P6) below --
    // `proptest` is a dev-dependency (the `proptest-dev-dependency` exclusion
    // class), so its macro bodies cannot be registered directly; each
    // property here reproduces the SAME assertion over a fixed, seeded
    // `SplitMix64` corpus. The native, randomized proptest module is
    // UNCHANGED and keeps exploring randomly.
    //
    // P6 (transitivity) constructs an increasing `a < b < c` chain directly
    // from the seed rather than drawing three independent floats and hoping
    // they land ordered (only ~1/6 of random triples would by chance) --
    // the uniform-sampling trap this task's own brief warns about. Every
    // seed below exercises the real transitivity check.
    use crate::wasm_campaign_prng::SplitMix64;

    fn campaign_normal_f64(rng: &mut SplitMix64) -> f64 {
        rng.range(-1e6, 1e6)
    }

    /// P1: For non-NaN f64, py_max returns the conventional maximum.
    fn p1_py_max_returns_larger_impl(seed: u64) {
        let mut rng = SplitMix64::new(seed);
        let a = campaign_normal_f64(&mut rng);
        let b = campaign_normal_f64(&mut rng);
        let r = py_max(a, b);
        let expected = if a >= b { a } else { b };
        assert_eq!(r, expected, "seed={seed}");
    }

    /// P2: py_max returns one of its inputs bit-identically.
    fn p2_py_max_returns_one_of_inputs_impl(seed: u64) {
        let mut rng = SplitMix64::new(seed);
        let a = campaign_normal_f64(&mut rng);
        let b = campaign_normal_f64(&mut rng);
        let r = py_max(a, b);
        assert!(r.to_bits() == a.to_bits() || r.to_bits() == b.to_bits(), "seed={seed}");
    }

    /// P3: Commutative for non-NaN inputs.
    fn p3_py_max_commutative_impl(seed: u64) {
        let mut rng = SplitMix64::new(seed);
        let a = campaign_normal_f64(&mut rng);
        let b = campaign_normal_f64(&mut rng);
        assert_eq!(py_max(a, b), py_max(b, a), "seed={seed}");
    }

    /// P4: For non-NaN, non-infinite floats, py_tuple_key_cmp ordering
    /// matches the numeric ordering of the first element, with the ref
    /// breaking ties.
    fn p4_tuple_cmp_matches_numeric_order_impl(seed: u64) {
        let mut rng = SplitMix64::new(seed);
        let a = campaign_normal_f64(&mut rng);
        let b = campaign_normal_f64(&mut rng);
        let ref_a = rng.ref_like();
        let ref_b = rng.ref_like();
        let ord = py_tuple_key_cmp(&a, &ref_a, &b, &ref_b);
        match a.partial_cmp(&b) {
            Some(std::cmp::Ordering::Equal) => assert_eq!(ord, ref_a.cmp(&ref_b), "seed={seed}"),
            Some(o) => assert_eq!(ord, o, "seed={seed}"),
            None => assert_eq!(ord, ref_a.cmp(&ref_b), "seed={seed}"),
        }
    }

    /// P5: Equal first elements always defer to the ref comparison.
    fn p5_equal_floats_defer_to_ref_impl(seed: u64) {
        let mut rng = SplitMix64::new(seed);
        let x = campaign_normal_f64(&mut rng);
        let ref_a = rng.ref_like();
        let ref_b = rng.ref_like();
        assert_eq!(py_tuple_key_cmp(&x, &ref_a, &x, &ref_b), ref_a.cmp(&ref_b), "seed={seed}");
    }

    /// P6: py_tuple_key_cmp is transitive for non-NaN floats. Builds an
    /// increasing `a < b < c` chain directly from the seed (see module note
    /// above) so every seed exercises the real check.
    fn p6_transitive_impl(seed: u64) {
        let mut rng = SplitMix64::new(seed);
        let a = rng.range(-1e5, 1e5);
        let delta1 = rng.range(1.0, 1e4);
        let delta2 = rng.range(1.0, 1e4);
        let b = a + delta1;
        let c = b + delta2;
        let ra = rng.ref_like();
        let rb = rng.ref_like();
        let rc = rng.ref_like();
        assert!(b > a && c > b, "seed={seed}");
        let ab = py_tuple_key_cmp(&a, &ra, &b, &rb);
        let bc = py_tuple_key_cmp(&b, &rb, &c, &rc);
        assert_eq!(ab, std::cmp::Ordering::Less, "seed={seed}");
        assert_eq!(bc, std::cmp::Ordering::Less, "seed={seed}");
        let ac = py_tuple_key_cmp(&a, &ra, &c, &rc);
        assert_ne!(
            ac,
            std::cmp::Ordering::Greater,
            "transitivity violated: ({a}, {ra}) < ({b}, {rb}) and ({b}, {rb}) < ({c}, {rc}) but ({a}, {ra}) > ({c}, {rc}) (seed={seed})"
        );
    }

    // --- BEGIN generated seeded property-mirror wrappers (deterministic proptest mirrors, R19/U6) ---
    // 6 properties x 20 seeds = 120 distinct-input wasm tests.
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
    fn p3_py_max_commutative_seed_000() { p3_py_max_commutative_impl(0); }
    #[cfg_attr(test, test)]
    fn p3_py_max_commutative_seed_001() { p3_py_max_commutative_impl(1); }
    #[cfg_attr(test, test)]
    fn p3_py_max_commutative_seed_002() { p3_py_max_commutative_impl(2); }
    #[cfg_attr(test, test)]
    fn p3_py_max_commutative_seed_003() { p3_py_max_commutative_impl(3); }
    #[cfg_attr(test, test)]
    fn p3_py_max_commutative_seed_004() { p3_py_max_commutative_impl(4); }
    #[cfg_attr(test, test)]
    fn p3_py_max_commutative_seed_005() { p3_py_max_commutative_impl(5); }
    #[cfg_attr(test, test)]
    fn p3_py_max_commutative_seed_006() { p3_py_max_commutative_impl(6); }
    #[cfg_attr(test, test)]
    fn p3_py_max_commutative_seed_007() { p3_py_max_commutative_impl(7); }
    #[cfg_attr(test, test)]
    fn p3_py_max_commutative_seed_008() { p3_py_max_commutative_impl(8); }
    #[cfg_attr(test, test)]
    fn p3_py_max_commutative_seed_009() { p3_py_max_commutative_impl(9); }
    #[cfg_attr(test, test)]
    fn p3_py_max_commutative_seed_010() { p3_py_max_commutative_impl(10); }
    #[cfg_attr(test, test)]
    fn p3_py_max_commutative_seed_011() { p3_py_max_commutative_impl(11); }
    #[cfg_attr(test, test)]
    fn p3_py_max_commutative_seed_012() { p3_py_max_commutative_impl(12); }
    #[cfg_attr(test, test)]
    fn p3_py_max_commutative_seed_013() { p3_py_max_commutative_impl(13); }
    #[cfg_attr(test, test)]
    fn p3_py_max_commutative_seed_014() { p3_py_max_commutative_impl(14); }
    #[cfg_attr(test, test)]
    fn p3_py_max_commutative_seed_015() { p3_py_max_commutative_impl(15); }
    #[cfg_attr(test, test)]
    fn p3_py_max_commutative_seed_016() { p3_py_max_commutative_impl(16); }
    #[cfg_attr(test, test)]
    fn p3_py_max_commutative_seed_017() { p3_py_max_commutative_impl(17); }
    #[cfg_attr(test, test)]
    fn p3_py_max_commutative_seed_018() { p3_py_max_commutative_impl(18); }
    #[cfg_attr(test, test)]
    fn p3_py_max_commutative_seed_019() { p3_py_max_commutative_impl(19); }
    #[cfg_attr(test, test)]
    fn p4_tuple_cmp_matches_numeric_order_seed_000() { p4_tuple_cmp_matches_numeric_order_impl(0); }
    #[cfg_attr(test, test)]
    fn p4_tuple_cmp_matches_numeric_order_seed_001() { p4_tuple_cmp_matches_numeric_order_impl(1); }
    #[cfg_attr(test, test)]
    fn p4_tuple_cmp_matches_numeric_order_seed_002() { p4_tuple_cmp_matches_numeric_order_impl(2); }
    #[cfg_attr(test, test)]
    fn p4_tuple_cmp_matches_numeric_order_seed_003() { p4_tuple_cmp_matches_numeric_order_impl(3); }
    #[cfg_attr(test, test)]
    fn p4_tuple_cmp_matches_numeric_order_seed_004() { p4_tuple_cmp_matches_numeric_order_impl(4); }
    #[cfg_attr(test, test)]
    fn p4_tuple_cmp_matches_numeric_order_seed_005() { p4_tuple_cmp_matches_numeric_order_impl(5); }
    #[cfg_attr(test, test)]
    fn p4_tuple_cmp_matches_numeric_order_seed_006() { p4_tuple_cmp_matches_numeric_order_impl(6); }
    #[cfg_attr(test, test)]
    fn p4_tuple_cmp_matches_numeric_order_seed_007() { p4_tuple_cmp_matches_numeric_order_impl(7); }
    #[cfg_attr(test, test)]
    fn p4_tuple_cmp_matches_numeric_order_seed_008() { p4_tuple_cmp_matches_numeric_order_impl(8); }
    #[cfg_attr(test, test)]
    fn p4_tuple_cmp_matches_numeric_order_seed_009() { p4_tuple_cmp_matches_numeric_order_impl(9); }
    #[cfg_attr(test, test)]
    fn p4_tuple_cmp_matches_numeric_order_seed_010() { p4_tuple_cmp_matches_numeric_order_impl(10); }
    #[cfg_attr(test, test)]
    fn p4_tuple_cmp_matches_numeric_order_seed_011() { p4_tuple_cmp_matches_numeric_order_impl(11); }
    #[cfg_attr(test, test)]
    fn p4_tuple_cmp_matches_numeric_order_seed_012() { p4_tuple_cmp_matches_numeric_order_impl(12); }
    #[cfg_attr(test, test)]
    fn p4_tuple_cmp_matches_numeric_order_seed_013() { p4_tuple_cmp_matches_numeric_order_impl(13); }
    #[cfg_attr(test, test)]
    fn p4_tuple_cmp_matches_numeric_order_seed_014() { p4_tuple_cmp_matches_numeric_order_impl(14); }
    #[cfg_attr(test, test)]
    fn p4_tuple_cmp_matches_numeric_order_seed_015() { p4_tuple_cmp_matches_numeric_order_impl(15); }
    #[cfg_attr(test, test)]
    fn p4_tuple_cmp_matches_numeric_order_seed_016() { p4_tuple_cmp_matches_numeric_order_impl(16); }
    #[cfg_attr(test, test)]
    fn p4_tuple_cmp_matches_numeric_order_seed_017() { p4_tuple_cmp_matches_numeric_order_impl(17); }
    #[cfg_attr(test, test)]
    fn p4_tuple_cmp_matches_numeric_order_seed_018() { p4_tuple_cmp_matches_numeric_order_impl(18); }
    #[cfg_attr(test, test)]
    fn p4_tuple_cmp_matches_numeric_order_seed_019() { p4_tuple_cmp_matches_numeric_order_impl(19); }
    #[cfg_attr(test, test)]
    fn p5_equal_floats_defer_to_ref_seed_000() { p5_equal_floats_defer_to_ref_impl(0); }
    #[cfg_attr(test, test)]
    fn p5_equal_floats_defer_to_ref_seed_001() { p5_equal_floats_defer_to_ref_impl(1); }
    #[cfg_attr(test, test)]
    fn p5_equal_floats_defer_to_ref_seed_002() { p5_equal_floats_defer_to_ref_impl(2); }
    #[cfg_attr(test, test)]
    fn p5_equal_floats_defer_to_ref_seed_003() { p5_equal_floats_defer_to_ref_impl(3); }
    #[cfg_attr(test, test)]
    fn p5_equal_floats_defer_to_ref_seed_004() { p5_equal_floats_defer_to_ref_impl(4); }
    #[cfg_attr(test, test)]
    fn p5_equal_floats_defer_to_ref_seed_005() { p5_equal_floats_defer_to_ref_impl(5); }
    #[cfg_attr(test, test)]
    fn p5_equal_floats_defer_to_ref_seed_006() { p5_equal_floats_defer_to_ref_impl(6); }
    #[cfg_attr(test, test)]
    fn p5_equal_floats_defer_to_ref_seed_007() { p5_equal_floats_defer_to_ref_impl(7); }
    #[cfg_attr(test, test)]
    fn p5_equal_floats_defer_to_ref_seed_008() { p5_equal_floats_defer_to_ref_impl(8); }
    #[cfg_attr(test, test)]
    fn p5_equal_floats_defer_to_ref_seed_009() { p5_equal_floats_defer_to_ref_impl(9); }
    #[cfg_attr(test, test)]
    fn p5_equal_floats_defer_to_ref_seed_010() { p5_equal_floats_defer_to_ref_impl(10); }
    #[cfg_attr(test, test)]
    fn p5_equal_floats_defer_to_ref_seed_011() { p5_equal_floats_defer_to_ref_impl(11); }
    #[cfg_attr(test, test)]
    fn p5_equal_floats_defer_to_ref_seed_012() { p5_equal_floats_defer_to_ref_impl(12); }
    #[cfg_attr(test, test)]
    fn p5_equal_floats_defer_to_ref_seed_013() { p5_equal_floats_defer_to_ref_impl(13); }
    #[cfg_attr(test, test)]
    fn p5_equal_floats_defer_to_ref_seed_014() { p5_equal_floats_defer_to_ref_impl(14); }
    #[cfg_attr(test, test)]
    fn p5_equal_floats_defer_to_ref_seed_015() { p5_equal_floats_defer_to_ref_impl(15); }
    #[cfg_attr(test, test)]
    fn p5_equal_floats_defer_to_ref_seed_016() { p5_equal_floats_defer_to_ref_impl(16); }
    #[cfg_attr(test, test)]
    fn p5_equal_floats_defer_to_ref_seed_017() { p5_equal_floats_defer_to_ref_impl(17); }
    #[cfg_attr(test, test)]
    fn p5_equal_floats_defer_to_ref_seed_018() { p5_equal_floats_defer_to_ref_impl(18); }
    #[cfg_attr(test, test)]
    fn p5_equal_floats_defer_to_ref_seed_019() { p5_equal_floats_defer_to_ref_impl(19); }
    #[cfg_attr(test, test)]
    fn p6_transitive_seed_000() { p6_transitive_impl(0); }
    #[cfg_attr(test, test)]
    fn p6_transitive_seed_001() { p6_transitive_impl(1); }
    #[cfg_attr(test, test)]
    fn p6_transitive_seed_002() { p6_transitive_impl(2); }
    #[cfg_attr(test, test)]
    fn p6_transitive_seed_003() { p6_transitive_impl(3); }
    #[cfg_attr(test, test)]
    fn p6_transitive_seed_004() { p6_transitive_impl(4); }
    #[cfg_attr(test, test)]
    fn p6_transitive_seed_005() { p6_transitive_impl(5); }
    #[cfg_attr(test, test)]
    fn p6_transitive_seed_006() { p6_transitive_impl(6); }
    #[cfg_attr(test, test)]
    fn p6_transitive_seed_007() { p6_transitive_impl(7); }
    #[cfg_attr(test, test)]
    fn p6_transitive_seed_008() { p6_transitive_impl(8); }
    #[cfg_attr(test, test)]
    fn p6_transitive_seed_009() { p6_transitive_impl(9); }
    #[cfg_attr(test, test)]
    fn p6_transitive_seed_010() { p6_transitive_impl(10); }
    #[cfg_attr(test, test)]
    fn p6_transitive_seed_011() { p6_transitive_impl(11); }
    #[cfg_attr(test, test)]
    fn p6_transitive_seed_012() { p6_transitive_impl(12); }
    #[cfg_attr(test, test)]
    fn p6_transitive_seed_013() { p6_transitive_impl(13); }
    #[cfg_attr(test, test)]
    fn p6_transitive_seed_014() { p6_transitive_impl(14); }
    #[cfg_attr(test, test)]
    fn p6_transitive_seed_015() { p6_transitive_impl(15); }
    #[cfg_attr(test, test)]
    fn p6_transitive_seed_016() { p6_transitive_impl(16); }
    #[cfg_attr(test, test)]
    fn p6_transitive_seed_017() { p6_transitive_impl(17); }
    #[cfg_attr(test, test)]
    fn p6_transitive_seed_018() { p6_transitive_impl(18); }
    #[cfg_attr(test, test)]
    fn p6_transitive_seed_019() { p6_transitive_impl(19); }
    // --- END generated seeded property-mirror wrappers ---

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("phased_assignment_stage::tests::py_max_nan_first_argument_wins", py_max_nan_first_argument_wins),
        ("phased_assignment_stage::tests::py_max_ties_keep_first", py_max_ties_keep_first),
        ("phased_assignment_stage::tests::py_max_infinity", py_max_infinity),
        ("phased_assignment_stage::tests::tuple_cmp_normal_floats", tuple_cmp_normal_floats),
        ("phased_assignment_stage::tests::tuple_cmp_nan_falls_through_to_ref", tuple_cmp_nan_falls_through_to_ref),
        ("phased_assignment_stage::tests::tuple_cmp_negative_zero_vs_zero", tuple_cmp_negative_zero_vs_zero),
        ("phased_assignment_stage::tests::tuple_cmp_infinity", tuple_cmp_infinity),
        ("phased_assignment_stage::tests::p1_py_max_returns_larger_seed_000", p1_py_max_returns_larger_seed_000),
        ("phased_assignment_stage::tests::p1_py_max_returns_larger_seed_001", p1_py_max_returns_larger_seed_001),
        ("phased_assignment_stage::tests::p1_py_max_returns_larger_seed_002", p1_py_max_returns_larger_seed_002),
        ("phased_assignment_stage::tests::p1_py_max_returns_larger_seed_003", p1_py_max_returns_larger_seed_003),
        ("phased_assignment_stage::tests::p1_py_max_returns_larger_seed_004", p1_py_max_returns_larger_seed_004),
        ("phased_assignment_stage::tests::p1_py_max_returns_larger_seed_005", p1_py_max_returns_larger_seed_005),
        ("phased_assignment_stage::tests::p1_py_max_returns_larger_seed_006", p1_py_max_returns_larger_seed_006),
        ("phased_assignment_stage::tests::p1_py_max_returns_larger_seed_007", p1_py_max_returns_larger_seed_007),
        ("phased_assignment_stage::tests::p1_py_max_returns_larger_seed_008", p1_py_max_returns_larger_seed_008),
        ("phased_assignment_stage::tests::p1_py_max_returns_larger_seed_009", p1_py_max_returns_larger_seed_009),
        ("phased_assignment_stage::tests::p1_py_max_returns_larger_seed_010", p1_py_max_returns_larger_seed_010),
        ("phased_assignment_stage::tests::p1_py_max_returns_larger_seed_011", p1_py_max_returns_larger_seed_011),
        ("phased_assignment_stage::tests::p1_py_max_returns_larger_seed_012", p1_py_max_returns_larger_seed_012),
        ("phased_assignment_stage::tests::p1_py_max_returns_larger_seed_013", p1_py_max_returns_larger_seed_013),
        ("phased_assignment_stage::tests::p1_py_max_returns_larger_seed_014", p1_py_max_returns_larger_seed_014),
        ("phased_assignment_stage::tests::p1_py_max_returns_larger_seed_015", p1_py_max_returns_larger_seed_015),
        ("phased_assignment_stage::tests::p1_py_max_returns_larger_seed_016", p1_py_max_returns_larger_seed_016),
        ("phased_assignment_stage::tests::p1_py_max_returns_larger_seed_017", p1_py_max_returns_larger_seed_017),
        ("phased_assignment_stage::tests::p1_py_max_returns_larger_seed_018", p1_py_max_returns_larger_seed_018),
        ("phased_assignment_stage::tests::p1_py_max_returns_larger_seed_019", p1_py_max_returns_larger_seed_019),
        ("phased_assignment_stage::tests::p2_py_max_returns_one_of_inputs_seed_000", p2_py_max_returns_one_of_inputs_seed_000),
        ("phased_assignment_stage::tests::p2_py_max_returns_one_of_inputs_seed_001", p2_py_max_returns_one_of_inputs_seed_001),
        ("phased_assignment_stage::tests::p2_py_max_returns_one_of_inputs_seed_002", p2_py_max_returns_one_of_inputs_seed_002),
        ("phased_assignment_stage::tests::p2_py_max_returns_one_of_inputs_seed_003", p2_py_max_returns_one_of_inputs_seed_003),
        ("phased_assignment_stage::tests::p2_py_max_returns_one_of_inputs_seed_004", p2_py_max_returns_one_of_inputs_seed_004),
        ("phased_assignment_stage::tests::p2_py_max_returns_one_of_inputs_seed_005", p2_py_max_returns_one_of_inputs_seed_005),
        ("phased_assignment_stage::tests::p2_py_max_returns_one_of_inputs_seed_006", p2_py_max_returns_one_of_inputs_seed_006),
        ("phased_assignment_stage::tests::p2_py_max_returns_one_of_inputs_seed_007", p2_py_max_returns_one_of_inputs_seed_007),
        ("phased_assignment_stage::tests::p2_py_max_returns_one_of_inputs_seed_008", p2_py_max_returns_one_of_inputs_seed_008),
        ("phased_assignment_stage::tests::p2_py_max_returns_one_of_inputs_seed_009", p2_py_max_returns_one_of_inputs_seed_009),
        ("phased_assignment_stage::tests::p2_py_max_returns_one_of_inputs_seed_010", p2_py_max_returns_one_of_inputs_seed_010),
        ("phased_assignment_stage::tests::p2_py_max_returns_one_of_inputs_seed_011", p2_py_max_returns_one_of_inputs_seed_011),
        ("phased_assignment_stage::tests::p2_py_max_returns_one_of_inputs_seed_012", p2_py_max_returns_one_of_inputs_seed_012),
        ("phased_assignment_stage::tests::p2_py_max_returns_one_of_inputs_seed_013", p2_py_max_returns_one_of_inputs_seed_013),
        ("phased_assignment_stage::tests::p2_py_max_returns_one_of_inputs_seed_014", p2_py_max_returns_one_of_inputs_seed_014),
        ("phased_assignment_stage::tests::p2_py_max_returns_one_of_inputs_seed_015", p2_py_max_returns_one_of_inputs_seed_015),
        ("phased_assignment_stage::tests::p2_py_max_returns_one_of_inputs_seed_016", p2_py_max_returns_one_of_inputs_seed_016),
        ("phased_assignment_stage::tests::p2_py_max_returns_one_of_inputs_seed_017", p2_py_max_returns_one_of_inputs_seed_017),
        ("phased_assignment_stage::tests::p2_py_max_returns_one_of_inputs_seed_018", p2_py_max_returns_one_of_inputs_seed_018),
        ("phased_assignment_stage::tests::p2_py_max_returns_one_of_inputs_seed_019", p2_py_max_returns_one_of_inputs_seed_019),
        ("phased_assignment_stage::tests::p3_py_max_commutative_seed_000", p3_py_max_commutative_seed_000),
        ("phased_assignment_stage::tests::p3_py_max_commutative_seed_001", p3_py_max_commutative_seed_001),
        ("phased_assignment_stage::tests::p3_py_max_commutative_seed_002", p3_py_max_commutative_seed_002),
        ("phased_assignment_stage::tests::p3_py_max_commutative_seed_003", p3_py_max_commutative_seed_003),
        ("phased_assignment_stage::tests::p3_py_max_commutative_seed_004", p3_py_max_commutative_seed_004),
        ("phased_assignment_stage::tests::p3_py_max_commutative_seed_005", p3_py_max_commutative_seed_005),
        ("phased_assignment_stage::tests::p3_py_max_commutative_seed_006", p3_py_max_commutative_seed_006),
        ("phased_assignment_stage::tests::p3_py_max_commutative_seed_007", p3_py_max_commutative_seed_007),
        ("phased_assignment_stage::tests::p3_py_max_commutative_seed_008", p3_py_max_commutative_seed_008),
        ("phased_assignment_stage::tests::p3_py_max_commutative_seed_009", p3_py_max_commutative_seed_009),
        ("phased_assignment_stage::tests::p3_py_max_commutative_seed_010", p3_py_max_commutative_seed_010),
        ("phased_assignment_stage::tests::p3_py_max_commutative_seed_011", p3_py_max_commutative_seed_011),
        ("phased_assignment_stage::tests::p3_py_max_commutative_seed_012", p3_py_max_commutative_seed_012),
        ("phased_assignment_stage::tests::p3_py_max_commutative_seed_013", p3_py_max_commutative_seed_013),
        ("phased_assignment_stage::tests::p3_py_max_commutative_seed_014", p3_py_max_commutative_seed_014),
        ("phased_assignment_stage::tests::p3_py_max_commutative_seed_015", p3_py_max_commutative_seed_015),
        ("phased_assignment_stage::tests::p3_py_max_commutative_seed_016", p3_py_max_commutative_seed_016),
        ("phased_assignment_stage::tests::p3_py_max_commutative_seed_017", p3_py_max_commutative_seed_017),
        ("phased_assignment_stage::tests::p3_py_max_commutative_seed_018", p3_py_max_commutative_seed_018),
        ("phased_assignment_stage::tests::p3_py_max_commutative_seed_019", p3_py_max_commutative_seed_019),
        ("phased_assignment_stage::tests::p4_tuple_cmp_matches_numeric_order_seed_000", p4_tuple_cmp_matches_numeric_order_seed_000),
        ("phased_assignment_stage::tests::p4_tuple_cmp_matches_numeric_order_seed_001", p4_tuple_cmp_matches_numeric_order_seed_001),
        ("phased_assignment_stage::tests::p4_tuple_cmp_matches_numeric_order_seed_002", p4_tuple_cmp_matches_numeric_order_seed_002),
        ("phased_assignment_stage::tests::p4_tuple_cmp_matches_numeric_order_seed_003", p4_tuple_cmp_matches_numeric_order_seed_003),
        ("phased_assignment_stage::tests::p4_tuple_cmp_matches_numeric_order_seed_004", p4_tuple_cmp_matches_numeric_order_seed_004),
        ("phased_assignment_stage::tests::p4_tuple_cmp_matches_numeric_order_seed_005", p4_tuple_cmp_matches_numeric_order_seed_005),
        ("phased_assignment_stage::tests::p4_tuple_cmp_matches_numeric_order_seed_006", p4_tuple_cmp_matches_numeric_order_seed_006),
        ("phased_assignment_stage::tests::p4_tuple_cmp_matches_numeric_order_seed_007", p4_tuple_cmp_matches_numeric_order_seed_007),
        ("phased_assignment_stage::tests::p4_tuple_cmp_matches_numeric_order_seed_008", p4_tuple_cmp_matches_numeric_order_seed_008),
        ("phased_assignment_stage::tests::p4_tuple_cmp_matches_numeric_order_seed_009", p4_tuple_cmp_matches_numeric_order_seed_009),
        ("phased_assignment_stage::tests::p4_tuple_cmp_matches_numeric_order_seed_010", p4_tuple_cmp_matches_numeric_order_seed_010),
        ("phased_assignment_stage::tests::p4_tuple_cmp_matches_numeric_order_seed_011", p4_tuple_cmp_matches_numeric_order_seed_011),
        ("phased_assignment_stage::tests::p4_tuple_cmp_matches_numeric_order_seed_012", p4_tuple_cmp_matches_numeric_order_seed_012),
        ("phased_assignment_stage::tests::p4_tuple_cmp_matches_numeric_order_seed_013", p4_tuple_cmp_matches_numeric_order_seed_013),
        ("phased_assignment_stage::tests::p4_tuple_cmp_matches_numeric_order_seed_014", p4_tuple_cmp_matches_numeric_order_seed_014),
        ("phased_assignment_stage::tests::p4_tuple_cmp_matches_numeric_order_seed_015", p4_tuple_cmp_matches_numeric_order_seed_015),
        ("phased_assignment_stage::tests::p4_tuple_cmp_matches_numeric_order_seed_016", p4_tuple_cmp_matches_numeric_order_seed_016),
        ("phased_assignment_stage::tests::p4_tuple_cmp_matches_numeric_order_seed_017", p4_tuple_cmp_matches_numeric_order_seed_017),
        ("phased_assignment_stage::tests::p4_tuple_cmp_matches_numeric_order_seed_018", p4_tuple_cmp_matches_numeric_order_seed_018),
        ("phased_assignment_stage::tests::p4_tuple_cmp_matches_numeric_order_seed_019", p4_tuple_cmp_matches_numeric_order_seed_019),
        ("phased_assignment_stage::tests::p5_equal_floats_defer_to_ref_seed_000", p5_equal_floats_defer_to_ref_seed_000),
        ("phased_assignment_stage::tests::p5_equal_floats_defer_to_ref_seed_001", p5_equal_floats_defer_to_ref_seed_001),
        ("phased_assignment_stage::tests::p5_equal_floats_defer_to_ref_seed_002", p5_equal_floats_defer_to_ref_seed_002),
        ("phased_assignment_stage::tests::p5_equal_floats_defer_to_ref_seed_003", p5_equal_floats_defer_to_ref_seed_003),
        ("phased_assignment_stage::tests::p5_equal_floats_defer_to_ref_seed_004", p5_equal_floats_defer_to_ref_seed_004),
        ("phased_assignment_stage::tests::p5_equal_floats_defer_to_ref_seed_005", p5_equal_floats_defer_to_ref_seed_005),
        ("phased_assignment_stage::tests::p5_equal_floats_defer_to_ref_seed_006", p5_equal_floats_defer_to_ref_seed_006),
        ("phased_assignment_stage::tests::p5_equal_floats_defer_to_ref_seed_007", p5_equal_floats_defer_to_ref_seed_007),
        ("phased_assignment_stage::tests::p5_equal_floats_defer_to_ref_seed_008", p5_equal_floats_defer_to_ref_seed_008),
        ("phased_assignment_stage::tests::p5_equal_floats_defer_to_ref_seed_009", p5_equal_floats_defer_to_ref_seed_009),
        ("phased_assignment_stage::tests::p5_equal_floats_defer_to_ref_seed_010", p5_equal_floats_defer_to_ref_seed_010),
        ("phased_assignment_stage::tests::p5_equal_floats_defer_to_ref_seed_011", p5_equal_floats_defer_to_ref_seed_011),
        ("phased_assignment_stage::tests::p5_equal_floats_defer_to_ref_seed_012", p5_equal_floats_defer_to_ref_seed_012),
        ("phased_assignment_stage::tests::p5_equal_floats_defer_to_ref_seed_013", p5_equal_floats_defer_to_ref_seed_013),
        ("phased_assignment_stage::tests::p5_equal_floats_defer_to_ref_seed_014", p5_equal_floats_defer_to_ref_seed_014),
        ("phased_assignment_stage::tests::p5_equal_floats_defer_to_ref_seed_015", p5_equal_floats_defer_to_ref_seed_015),
        ("phased_assignment_stage::tests::p5_equal_floats_defer_to_ref_seed_016", p5_equal_floats_defer_to_ref_seed_016),
        ("phased_assignment_stage::tests::p5_equal_floats_defer_to_ref_seed_017", p5_equal_floats_defer_to_ref_seed_017),
        ("phased_assignment_stage::tests::p5_equal_floats_defer_to_ref_seed_018", p5_equal_floats_defer_to_ref_seed_018),
        ("phased_assignment_stage::tests::p5_equal_floats_defer_to_ref_seed_019", p5_equal_floats_defer_to_ref_seed_019),
        ("phased_assignment_stage::tests::p6_transitive_seed_000", p6_transitive_seed_000),
        ("phased_assignment_stage::tests::p6_transitive_seed_001", p6_transitive_seed_001),
        ("phased_assignment_stage::tests::p6_transitive_seed_002", p6_transitive_seed_002),
        ("phased_assignment_stage::tests::p6_transitive_seed_003", p6_transitive_seed_003),
        ("phased_assignment_stage::tests::p6_transitive_seed_004", p6_transitive_seed_004),
        ("phased_assignment_stage::tests::p6_transitive_seed_005", p6_transitive_seed_005),
        ("phased_assignment_stage::tests::p6_transitive_seed_006", p6_transitive_seed_006),
        ("phased_assignment_stage::tests::p6_transitive_seed_007", p6_transitive_seed_007),
        ("phased_assignment_stage::tests::p6_transitive_seed_008", p6_transitive_seed_008),
        ("phased_assignment_stage::tests::p6_transitive_seed_009", p6_transitive_seed_009),
        ("phased_assignment_stage::tests::p6_transitive_seed_010", p6_transitive_seed_010),
        ("phased_assignment_stage::tests::p6_transitive_seed_011", p6_transitive_seed_011),
        ("phased_assignment_stage::tests::p6_transitive_seed_012", p6_transitive_seed_012),
        ("phased_assignment_stage::tests::p6_transitive_seed_013", p6_transitive_seed_013),
        ("phased_assignment_stage::tests::p6_transitive_seed_014", p6_transitive_seed_014),
        ("phased_assignment_stage::tests::p6_transitive_seed_015", p6_transitive_seed_015),
        ("phased_assignment_stage::tests::p6_transitive_seed_016", p6_transitive_seed_016),
        ("phased_assignment_stage::tests::p6_transitive_seed_017", p6_transitive_seed_017),
        ("phased_assignment_stage::tests::p6_transitive_seed_018", p6_transitive_seed_018),
        ("phased_assignment_stage::tests::p6_transitive_seed_019", p6_transitive_seed_019),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}

// `proptest` is a dev-dependency (present under `cargo test`, absent from the
// ordinary non-test build `wasm_test_registry.rs` compiles into), so these
// six properties live in their own `#[cfg(test)]` sibling module -- exactly
// the split `copper_length.rs`/`timing.rs`/`host_math.rs` already use --
// rather than inline inside `tests` above, so `gen_wasm_test_registry.py`'s
// per-module `proptest-dev-dependency` exclusion only drops these six
// properties instead of the whole module's otherwise-pure `py_max` /
// `py_tuple_key_cmp` unit tests.
#[cfg(test)]
mod proptests {
    use super::*;
    use proptest::prelude::*;

    fn normal_f64() -> impl Strategy<Value = f64> {
        prop::num::f64::NORMAL
    }

    proptest! {
        /// P1: For non-NaN f64, py_max returns the conventional maximum.
        #[test]
        fn p1_py_max_returns_larger(a in normal_f64(), b in normal_f64()) {
            let r = py_max(a, b);
            let expected = if a >= b { a } else { b };
            prop_assert_eq!(r, expected);
        }

        /// P2: py_max returns one of its inputs bit-identically.
        #[test]
        fn p2_py_max_returns_one_of_inputs(a in normal_f64(), b in normal_f64()) {
            let r = py_max(a, b);
            prop_assert!(r.to_bits() == a.to_bits() || r.to_bits() == b.to_bits());
        }

        /// P3: Commutative for non-NaN inputs.
        #[test]
        fn p3_py_max_commutative(a in normal_f64(), b in normal_f64()) {
            prop_assert_eq!(py_max(a, b), py_max(b, a));
        }

        /// P4: For non-NaN, non-infinite floats, py_tuple_key_cmp ordering
        /// matches the numeric ordering of the first element, with the ref
        /// breaking ties.
        #[test]
        fn p4_tuple_cmp_matches_numeric_order(
            a in normal_f64(), b in normal_f64(),
            ref_a in "[A-Z][0-9]", ref_b in "[A-Z][0-9]",
        ) {
            let ord = py_tuple_key_cmp(&a, &ref_a, &b, &ref_b);
            match a.partial_cmp(&b) {
                Some(std::cmp::Ordering::Equal) => {
                    prop_assert_eq!(ord, ref_a.cmp(&ref_b));
                }
                Some(o) => {
                    prop_assert_eq!(ord, o);
                }
                None => {
                    prop_assert_eq!(ord, ref_a.cmp(&ref_b));
                }
            }
        }

        /// P5: Equal first elements always defer to the ref comparison.
        #[test]
        fn p5_equal_floats_defer_to_ref(
            x in normal_f64(),
            ref_a in "[A-Z][0-9]", ref_b in "[A-Z][0-9]",
        ) {
            prop_assert_eq!(
                py_tuple_key_cmp(&x, &ref_a, &x, &ref_b),
                ref_a.cmp(&ref_b)
            );
        }

        /// P6: py_tuple_key_cmp is transitive for non-NaN floats (the sort
        /// must produce a total order).
        #[test]
        fn p6_transitive(
            a in normal_f64(), b in normal_f64(), c in normal_f64(),
            ra in "[A-Z][0-9]", rb in "[A-Z][0-9]", rc in "[A-Z][0-9]",
        ) {
            let ab = py_tuple_key_cmp(&a, &ra, &b, &rb);
            let bc = py_tuple_key_cmp(&b, &rb, &c, &rc);
            if ab == std::cmp::Ordering::Less && bc == std::cmp::Ordering::Less {
                let ac = py_tuple_key_cmp(&a, &ra, &c, &rc);
                prop_assert!(ac != std::cmp::Ordering::Greater,
                    "transitivity violated: ({}, {}) < ({}, {}) and ({}, {}) < ({}, {}) but ({}, {}) > ({}, {})",
                    a, ra, b, rb, b, rb, c, rc, a, ra, c, rc);
            }
        }
    }
}
