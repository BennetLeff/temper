// The D5 `ZoneAwareSlotGenerationStage` of the Rust Orchestration Engine plan
// (2026-08-09-001, Phase D batch D5): a `Stage<BoardState>` implementor
// mirroring `deterministic/stages/zone_aware_slot_generation.py`.
//
// The whole run() orchestration moves to Rust: the isolation-slot filter
// (`_isolation_filter`: the netlist `comp_pos` / `comp_by_ref` lookups, the
// K4 reclaim formula with `_hv_clearance_overrides` and the per-slot pin
// pitch resolution, the AABB build), the copper-zone collection
// (`_get_copper_zones`: YAML + board.copper_zones + board.zones with the
// POWER_NET_NAMES net-class classification), the no-filter plain-generation
// branch, the per-zone slot walk with the copper + isolation-cutout filters,
// the F.Cu/statistics log lines and the `frozenset(zone_slots_list)` +
// `reclaim_by_pin_pair` writes.
//
// What stays Python / single-source (driven through FFI, bit-exact by
// construction):
// - the slot-grid kernel (`temper_design_bundle_python.deterministic_stages
//   .generate_slots_for_zone`), the `point_in_polygon_py` ray casting, the
//   `slot_intersects_iso_py` AABB test (all Wave-4 Phase-5 final leaves),
// - `isolation_slot_aabb` (`temper_placer.io.isolation_slot_geometry`,
//   re-exported from temper_io_types),
// - the `POWER_NET_NAMES` net-name classification set (the module constant —
//   the SSOT for copper-zone net-class matching),
// - the `_hv_clearance_overrides` regex (CPython `re`, driven via FFI — the
//   word-boundary pattern and `"HIGHVOLTAGE" in key` semantics),
// - CPython `str.format` for every interpolated log message (David-Gay
//   `:.1f`/`:.2f` and list-repr rendering).
//
// Bit-exactness notes:
// - `_resolve_pin_pitch_mm` closes with `** 0.5` over `** 2` squares --
//   CPython `float ** float` is libm `pow`, routed through `host_math::pow`.
// - `max`/`min` are CPython first-arg-wins (`py_max`/`py_min`), never
//   `f64::max`.
// - the reclaim dict insertion order is the isolation-slot list order; the
//   `frozenset(zone_slots_list)` is built via builtins over the per-zone
//   entries exactly like the oracle.
// - `state.zones` truthiness is the Python guard; the no-zones path writes
//   `reclaim or None` (an empty dict -> Python None, value-identical to the
//   oracle's `dataclasses.replace`).

use std::borrow::Cow;

use pyo3::prelude::*;
use pyo3::types::{PyDict, PyFloat, PyList, PyString, PyTuple};

use crate::board_state::BoardState;
use crate::config_attach_stage::to_pyerr;
use crate::derivation_stage::{pyerr_stage, stage_guard};
use crate::grid_hv::{getattr_default, str_py};
use crate::host_math;
use crate::stage::{Stage, StageError};

const STAGE_NAME: &str = "zone_aware_slot_generation";
const LOGGER_NAME: &str = "temper_placer.deterministic.stages.zone_aware_slot_generation";
const PLACEMENT_LAYER: &str = "F.Cu";

// @req(2026-06-23-007, R2/K4): the K4 reclaim formula constants.
const K4_PERPENDICULAR_CLEARANCE_BUDGET_MM: f64 = 5.5;
const K4_ORIGINAL_REQUIREMENT_MM: f64 = 6.0;
// @req(2026-06-23-007, R2/K4): the TO-247 pin-1 to pin-2 pitch fallback.
const K4_TO247_PIN_PITCH_DEFAULT_MM: f64 = 5.45;

/// The zone-aware slot-generation stage: zones + board + netlist ->
/// `zone_slots` (frozenset of `(zone_name, tuple_of_slots)`, copper-zone and
/// isolation-cutout filtered) + `reclaim_by_pin_pair` (the K4 reclaim dict,
/// or None).
#[derive(Debug, Clone)]
pub struct ZoneAwareSlotGenerationStage {
    pub slot_spacing_mm: f64,
    pub copper_zone_margin: f64,
    pub yaml_copper_zones: Option<Py<PyAny>>,
    pub yaml_isolation_slots: Option<Py<PyAny>>,
    pub net_class_rules: Option<Py<PyAny>>,
}

impl Stage<BoardState> for ZoneAwareSlotGenerationStage {
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

impl ZoneAwareSlotGenerationStage {
    /// The stage body. `state.zones` falsy -> the isolation filter still runs
    /// and the reclaim (or None) is written, exactly like the oracle.
    fn run_inner(&self, py: Python<'_>, state: BoardState) -> PyResult<BoardState> {
        let (iso_aabbs, reclaim) = self.isolation_filter(py, &state)?;

        let zones = match &state.zones {
            Some(z) if z.bind(py).is_truthy()? => z.clone_ref(py),
            _ => {
                let mut new_state = state;
                new_state.reclaim_by_pin_pair = reclaim_or_none(py, reclaim)?;
                return Ok(new_state);
            }
        };

        let copper_zones = self.get_copper_zones(py, &state)?;
        let has_copper = copper_zones.len() > 0;
        let has_iso = iso_aabbs.len() > 0;

        if !has_copper && !has_iso {
            // `logger.info("No copper zones or isolation slots, using standard slot generation")`
            log_msg(py, "info", &PyString::new(py, "No copper zones or isolation slots, using standard slot generation").into_any())?;
            let zone_slots = plain_generation(py, zones.bind(py), self.slot_spacing_mm)?;
            let mut new_state = state;
            new_state.zone_slots = Some(zone_slots);
            new_state.reclaim_by_pin_pair = None;
            return Ok(new_state);
        }

        if has_copper {
            self.log_fcu_zones(py, &copper_zones)?;
        }

        let tdb = py.import("temper_design_bundle_python")?.getattr("deterministic_stages")?;
        let builtins = py.import("builtins")?;

        let zone_slots_list = PyList::empty(py);
        let mut total_slots: i64 = 0;
        let mut copper_filtered: i64 = 0;
        let mut iso_filtered: i64 = 0;

        for zone in zones.bind(py).try_iter()? {
            let zone = zone?;
            let all_slots = generate_slots_for_zone(py, &zone, self.slot_spacing_mm, &tdb)?;
            let valid_slots = PyList::empty(py);
            for slot in all_slots.try_iter()? {
                let slot = slot?;
                if self.is_slot_in_copper_zone(py, &slot, &copper_zones)? {
                    copper_filtered += 1;
                    continue;
                }
                if slot_intersects_iso(py, &slot, &iso_aabbs)? {
                    iso_filtered += 1;
                    continue;
                }
                valid_slots.append(slot)?;
            }
            total_slots += all_slots.len()? as i64;
            let slot_tuple = builtins.getattr("tuple")?.call1((valid_slots,))?;
            let entry = PyTuple::new(py, [zone.getattr("name")?, slot_tuple])?;
            zone_slots_list.append(entry)?;
        }

        if has_copper {
            let ratio = (100.0 * copper_filtered as f64) / total_slots.max(1) as f64;
            let msg = py_format(
                py,
                "Slot filtering: copper_zone_filtered={} of {} total ({:.1f}%)",
                &[
                    copper_filtered.into_pyobject(py)?.into_any(),
                    total_slots.into_pyobject(py)?.into_any(),
                    PyFloat::new(py, ratio).into_any(),
                ],
            )?;
            log_msg(py, "info", &msg)?;
        }
        if has_iso {
            let ratio = (100.0 * iso_filtered as f64) / total_slots.max(1) as f64;
            let msg = py_format(
                py,
                "Slot filtering: isolation_slot_filtered={} of {} total ({:.1f}%)",
                &[
                    iso_filtered.into_pyobject(py)?.into_any(),
                    total_slots.into_pyobject(py)?.into_any(),
                    PyFloat::new(py, ratio).into_any(),
                ],
            )?;
            log_msg(py, "info", &msg)?;
            let total_reclaim: f64 = match &reclaim {
                Some(d) => {
                    let mut acc = 0.0f64;
                    for item in d.bind(py).call_method0("values")?.try_iter()? {
                        acc += item?.extract::<f64>()?;
                    }
                    acc
                }
                None => 0.0,
            };
            let msg = py_format(
                py,
                "Isolation slots reclaim {:.2f}mm of routing channel",
                &[PyFloat::new(py, total_reclaim).into_any()],
            )?;
            log_msg(py, "info", &msg)?;
        }

        let mut new_state = state;
        new_state.zone_slots = Some(
            builtins
                .getattr("frozenset")?
                .call1((zone_slots_list,))?
                .into_any()
                .unbind(),
        );
        new_state.reclaim_by_pin_pair = reclaim_or_none(py, reclaim)?;
        Ok(new_state)
    }

    /// `_isolation_filter`: the per-component position/object lookups, the
    /// HV clearance overrides, and the AABB + K4 reclaim loop. Returns
    /// `(iso_aabbs list, reclaim dict or None)`.
    fn isolation_filter<'py>(
        &self,
        py: Python<'py>,
        state: &BoardState,
    ) -> PyResult<(Bound<'py, PyList>, Option<Py<PyAny>>)> {
        let empty = PyList::empty(py);
        let yaml_iso: Bound<'py, PyAny> = match &self.yaml_isolation_slots {
            Some(l) => l.bind(py).clone(),
            None => empty.clone().into_any(),
        };
        if yaml_iso.len()? == 0 {
            return Ok((empty, None));
        }

        let comp_pos = PyDict::new(py);
        let comp_by_ref = PyDict::new(py);
        if let Some(nl) = &state.netlist {
            for component in nl.bind(py).getattr("components")?.try_iter()? {
                let component = component?;
                let ref_val = component.getattr("ref")?;
                comp_by_ref.set_item(&ref_val, &component)?;
                let ip = component.getattr("initial_position")?;
                if !ip.is_none() {
                    let pos = PyTuple::new(py, [ip.get_item(0)?, ip.get_item(1)?])?;
                    comp_pos.set_item(&ref_val, pos)?;
                }
            }
        }

        let (perp_budget, original_req) = hv_clearance_overrides(py, &self.net_class_rules)?;

        let aabbs = PyList::empty(py);
        let reclaim = PyDict::new(py);
        let iso_aabb_fn = py
            .import("temper_placer.io.isolation_slot_geometry")?
            .getattr("isolation_slot_aabb")?;
        for slot in yaml_iso.try_iter()? {
            let slot = slot?;
            let comp_ref = slot.getattr("component_ref")?;
            let lv_pin = slot.getattr("lv_pin")?;
            let hv_pin = slot.getattr("hv_pin")?;
            let comp_xy = comp_pos.call_method1("get", (&comp_ref,))?;
            if comp_xy.is_none() {
                continue;
            }
            aabbs.append(iso_aabb_fn.call1((&slot, &comp_xy))?)?;
            let comp = comp_by_ref.call_method1("get", (&comp_ref,))?;
            let comp = if comp.is_none() { None } else { Some(comp) };
            let pin_pitch_mm = resolve_pin_pitch_mm(comp.as_ref(), &lv_pin, &hv_pin)?;
            let width: f64 = slot.getattr("width_mm")?.extract()?;
            let raw = width / 2.0 + perp_budget - pin_pitch_mm;
            let upper = py_max(0.0, original_req - 0.5);
            let reclaim_value = py_max(0.0, py_min(raw, upper));
            let key = PyTuple::new(py, [comp_ref, lv_pin, hv_pin])?;
            reclaim.set_item(key, PyFloat::new(py, reclaim_value))?;
        }
        Ok((aabbs, Some(reclaim.into_any().unbind())))
    }

    /// `_get_copper_zones`: YAML zones first, then `board.copper_zones`,
    /// then the `board.zones` net-class / polygon scan.
    fn get_copper_zones<'py>(
        &self,
        py: Python<'py>,
        state: &BoardState,
    ) -> PyResult<Bound<'py, PyList>> {
        let empty = PyList::empty(py);
        let yaml_zones: Bound<'py, PyAny> = match &self.yaml_copper_zones {
            Some(l) => l.bind(py).clone(),
            None => empty.clone().into_any(),
        };
        let has_board = match &state.board {
            Some(b) => b.bind(py).is_truthy()?,
            None => false,
        };
        if !has_board && yaml_zones.len()? == 0 {
            return Ok(empty);
        }

        let copper_zones = PyList::empty(py);
        if yaml_zones.len()? > 0 {
            copper_zones.call_method1("extend", (&yaml_zones,))?;
            let msg = py_format(
                py,
                "Added {} copper zones from YAML config",
                &[yaml_zones.len()?.into_pyobject(py)?.into_any()],
            )?;
            log_msg(py, "debug", &msg)?;
        }

        let board = match &state.board {
            Some(b) => b.bind(py),
            None => return Ok(copper_zones),
        };

        // Option 1: board.copper_zones.
        if board.hasattr("copper_zones")? && board.getattr("copper_zones")?.is_truthy()? {
            let bcz = board.getattr("copper_zones")?;
            copper_zones.call_method1("extend", (&bcz,))?;
            let msg = py_format(
                py,
                "Added {} from board.copper_zones",
                &[bcz.len()?.into_pyobject(py)?.into_any()],
            )?;
            log_msg(py, "debug", &msg)?;
        }

        // Option 2: board.zones (net-class / polygon scan).
        if board.hasattr("zones")? && board.getattr("zones")?.is_truthy()? {
            let power_names = py
                .import("temper_placer.deterministic.stages.zone_aware_slot_generation")?
                .getattr("POWER_NET_NAMES")?;
            for zone in board.getattr("zones")?.try_iter()? {
                let zone = zone?;
                if zone.hasattr("net_classes")? && zone.getattr("net_classes")?.is_truthy()? {
                    let ncs = zone.getattr("net_classes")?;
                    for net_class in ncs.try_iter()? {
                        let net_class = net_class?;
                        let key = net_class.call_method0("upper")?;
                        let is_power: bool = power_names
                            .call_method1("__contains__", (&key,))?
                            .extract()?;
                        if is_power {
                            copper_zones.append(&zone)?;
                            let name = if zone.hasattr("name")? {
                                zone.getattr("name")?
                            } else {
                                str_py(py, "unnamed").bind(py).clone()
                            };
                            let ncs = zone.getattr("net_classes")?;
                            let msg = py_format(
                                py,
                                "Found copper zone: {} with net_classes={}",
                                &[name.into_any(), ncs.into_any()],
                            )?;
                            log_msg(py, "debug", &msg)?;
                            break;
                        }
                    }
                } else if zone.hasattr("polygon")?
                    && zone.getattr("polygon")?.is_truthy()?
                    && !copper_zones.contains(&zone)?
                {
                    copper_zones.append(&zone)?;
                    let name = if zone.hasattr("name")? {
                        zone.getattr("name")?
                    } else {
                        str_py(py, "unnamed").bind(py).clone()
                    };
                    let msg = py_format(
                        py,
                        "Found copper zone with polygon: {}",
                        &[name.into_any()],
                    )?;
                    log_msg(py, "debug", &msg)?;
                }
            }
        }
        Ok(copper_zones)
    }

    /// The F.Cu classification + the two INFO lines when copper zones exist.
    fn log_fcu_zones<'py>(
        &self,
        py: Python<'py>,
        copper_zones: &Bound<'py, PyList>,
    ) -> PyResult<()> {
        let msg = py_format(
            py,
            "Found {} copper zones, filtering slots",
            &[copper_zones.len().into_pyobject(py)?.into_any()],
        )?;
        log_msg(py, "info", &msg)?;

        let fcu_zones = PyList::empty(py);
        let other_zones = PyList::empty(py);
        for cz in copper_zones.try_iter()? {
            let cz = cz?;
            let zone_name = getattr_default(py, &cz, "name", str_py(py, "unnamed"))?;
            let zone_layers = getattr_default(py, &cz, "layers", py.None())?;
            if zone_layers.is_truthy()? {
                let layers: Bound<'py, PyAny> = if zone_layers.is_instance_of::<PyString>() {
                    let single = PyList::empty(py);
                    single.append(&zone_layers)?;
                    single.into_any()
                } else {
                    zone_layers.clone()
                };
                let on_fcu: bool = layers
                    .call_method1("__contains__", (PLACEMENT_LAYER,))?
                    .extract()?;
                if on_fcu {
                    fcu_zones.append(&zone_name)?;
                } else {
                    let entry = py_format(
                        py,
                        "{}({})",
                        &[zone_name.into_any(), zone_layers.into_any()],
                    )?;
                    other_zones.append(entry)?;
                }
            } else {
                let entry = py_format(py, "{}(no layer)", &[zone_name.into_any()])?;
                fcu_zones.append(entry)?;
            }
        }
        if other_zones.len() > 0 {
            let msg = py_format(
                py,
                "Skipping {} copper zones not on F.Cu: {}",
                &[
                    other_zones.len().into_pyobject(py)?.into_any(),
                    other_zones.into_any(),
                ],
            )?;
            log_msg(py, "info", &msg)?;
        }
        if fcu_zones.len() > 0 {
            let msg = py_format(
                py,
                "Filtering slots for {} F.Cu copper zones: {}",
                &[
                    fcu_zones.len().into_pyobject(py)?.into_any(),
                    fcu_zones.into_any(),
                ],
            )?;
            log_msg(py, "info", &msg)?;
        }
        Ok(())
    }

    /// `_is_slot_in_copper_zone`: per-zone layer skip, then the polygon
    /// containment test (design-bundle kernel), then the bounds-margin box.
    fn is_slot_in_copper_zone<'py>(
        &self,
        py: Python<'py>,
        slot: &Bound<'py, PyAny>,
        copper_zones: &Bound<'py, PyAny>,
    ) -> PyResult<bool> {
        let x: f64 = slot.get_item(0)?.extract()?;
        let y: f64 = slot.get_item(1)?.extract()?;
        let pip = py
            .import("temper_design_bundle_python")?
            .getattr("deterministic_phase")?
            .getattr("point_in_polygon_py")?;

        for zone in copper_zones.try_iter()? {
            let zone = zone?;
            if zone.hasattr("layers")? {
                let layers = zone.getattr("layers")?;
                if layers.is_truthy()? {
                    let layers: Bound<'py, PyAny> = if layers.is_instance_of::<PyString>() {
                        let single = PyList::empty(py);
                        single.append(&layers)?;
                        single.into_any()
                    } else {
                        layers.clone()
                    };
                    let on_layer: bool = layers
                        .call_method1("__contains__", (PLACEMENT_LAYER,))?
                        .extract()?;
                    if !on_layer {
                        continue;
                    }
                }
            }
            let has_polygon = zone.hasattr("polygon")? && {
                let p = zone.getattr("polygon")?;
                p.is_truthy()?
            };
            if has_polygon {
                let polygon = zone.getattr("polygon")?;
                let inside: bool = pip.call1((x, y, &polygon))?.extract()?;
                if inside {
                    return Ok(true);
                }
            } else if zone.hasattr("bounds")? {
                let bounds = zone.getattr("bounds")?;
                if bounds.is_truthy()? {
                    let (mut x_min, mut y_min, mut x_max, mut y_max): (f64, f64, f64, f64) =
                        match bounds.len()? {
                            4 => (
                                bounds.get_item(0)?.extract()?,
                                bounds.get_item(1)?.extract()?,
                                bounds.get_item(2)?.extract()?,
                                bounds.get_item(3)?.extract()?,
                            ),
                            2 => {
                                let lo = bounds.get_item(0)?;
                                let hi = bounds.get_item(1)?;
                                (
                                    lo.get_item(0)?.extract()?,
                                    lo.get_item(1)?.extract()?,
                                    hi.get_item(0)?.extract()?,
                                    hi.get_item(1)?.extract()?,
                                )
                            }
                            _ => continue,
                        };
                    x_min -= self.copper_zone_margin;
                    y_min -= self.copper_zone_margin;
                    x_max += self.copper_zone_margin;
                    y_max += self.copper_zone_margin;
                    if x_min <= x && x <= x_max && y_min <= y && y <= y_max {
                        return Ok(true);
                    }
                }
            }
        }
        Ok(false)
    }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/// `reclaim or None`: an empty reclaim dict is falsy -> Python None.
fn reclaim_or_none(py: Python<'_>, reclaim: Option<Py<PyAny>>) -> PyResult<Option<Py<PyAny>>> {
    match reclaim {
        Some(d) => {
            if d.bind(py).len()? == 0 {
                Ok(None)
            } else {
                Ok(Some(d))
            }
        }
        None => Ok(None),
    }
}

/// The no-filter branch: `(zone.name, tuple(generate_slots_for_zone(...)))`
/// per zone, wrapped in a frozenset.
fn plain_generation<'py>(
    py: Python<'py>,
    zones: &Bound<'py, PyAny>,
    spacing: f64,
) -> PyResult<Py<PyAny>> {
    let tdb = py.import("temper_design_bundle_python")?.getattr("deterministic_stages")?;
    let builtins = py.import("builtins")?;
    let zone_slots_list = PyList::empty(py);
    for zone in zones.try_iter()? {
        let zone = zone?;
        let all_slots = generate_slots_for_zone(py, &zone, spacing, &tdb)?;
        let slot_tuple = builtins.getattr("tuple")?.call1((all_slots,))?;
        let entry = PyTuple::new(py, [zone.getattr("name")?, slot_tuple])?;
        zone_slots_list.append(entry)?;
    }
    Ok(builtins
        .getattr("frozenset")?
        .call1((zone_slots_list,))?
        .into_any()
        .unbind())
}

/// `list(_tdb.deterministic_stages.generate_slots_for_zone(x_min, y_min,
/// x_max, y_max, spacing))` -- the Phase-5 slot-grid kernel call.
fn generate_slots_for_zone<'py>(
    py: Python<'py>,
    zone: &Bound<'py, PyAny>,
    spacing: f64,
    tdb: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let bounds = zone.getattr("bounds")?;
    let lo = bounds.get_item(0)?;
    let hi = bounds.get_item(1)?;
    let x_min: f64 = lo.get_item(0)?.extract()?;
    let y_min: f64 = lo.get_item(1)?.extract()?;
    let x_max: f64 = hi.get_item(0)?.extract()?;
    let y_max: f64 = hi.get_item(1)?.extract()?;
    let slots = tdb.call_method1("generate_slots_for_zone", (x_min, y_min, x_max, y_max, spacing))?;
    let list = py.import("builtins")?.getattr("list")?.call1((slots,))?;
    Ok(list)
}

/// `_slot_intersects_iso` -- the design-bundle AABB kernel.
fn slot_intersects_iso<'py>(
    py: Python<'py>,
    slot: &Bound<'py, PyAny>,
    iso_aabbs: &Bound<'py, PyList>,
) -> PyResult<bool> {
    let f = py
        .import("temper_design_bundle_python")?
        .getattr("deterministic_phase")?
        .getattr("slot_intersects_iso_py")?;
    Ok(f.call1((slot, iso_aabbs))?.extract()?)
}

/// `_hv_clearance_overrides`: the HV word-boundary regex scan of the
/// uppercased class names; `(perp_budget, original_req)` defaults on no match.
fn hv_clearance_overrides(
    py: Python<'_>,
    net_class_rules: &Option<Py<PyAny>>,
) -> PyResult<(f64, f64)> {
    let defaults = (
        K4_PERPENDICULAR_CLEARANCE_BUDGET_MM,
        K4_ORIGINAL_REQUIREMENT_MM,
    );
    let rules = match net_class_rules {
        Some(r) => r.bind(py),
        None => return Ok(defaults),
    };
    if rules.len()? == 0 {
        return Ok(defaults);
    }
    let re_mod = py.import("re")?;
    for (class_name, rule) in dict_items(py, rules)? {
        let key = class_name.bind(py).str()?.call_method0("upper")?;
        let hv_re: bool = re_mod
            .call_method1("search", ("(?:^|_)HV(?:$|[\\d_])", &key))?
            .is_truthy()?;
        let hv_hl: bool = key
            .call_method1("__contains__", ("HIGHVOLTAGE",))?
            .extract()?;
        if hv_re || hv_hl {
            let clearance = getattr_default(py, rule.bind(py), "clearance_mm", py.None())?;
            let is_num = clearance.is_instance_of::<pyo3::types::PyFloat>()
                || clearance.is_instance_of::<pyo3::types::PyInt>();
            if is_num {
                let c: f64 = clearance.extract()?;
                if c > 0.0 {
                    return Ok((c, c));
                }
            }
        }
    }
    Ok(defaults)
}

/// `_resolve_pin_pitch_mm`: the placed component's lv/hv pin pitch (pow
/// arithmetic), or the TO-247 fallback.
fn resolve_pin_pitch_mm<'py>(
    comp: Option<&Bound<'py, PyAny>>,
    lv_pin: &Bound<'py, PyAny>,
    hv_pin: &Bound<'py, PyAny>,
) -> PyResult<f64> {
    let comp = match comp {
        Some(c) => c,
        None => return Ok(K4_TO247_PIN_PITCH_DEFAULT_MM),
    };
    if !lv_pin.is_truthy()? || !hv_pin.is_truthy()? {
        return Ok(K4_TO247_PIN_PITCH_DEFAULT_MM);
    }
    if !comp.hasattr("get_pin")? {
        return Ok(K4_TO247_PIN_PITCH_DEFAULT_MM);
    }
    let get_pin = comp.getattr("get_pin")?;
    if get_pin.is_none() {
        return Ok(K4_TO247_PIN_PITCH_DEFAULT_MM);
    }
    let lv = get_pin.call1((lv_pin,))?;
    let hv = get_pin.call1((hv_pin,))?;
    if lv.is_none() || hv.is_none() {
        return Ok(K4_TO247_PIN_PITCH_DEFAULT_MM);
    }
    let lv_pos = lv.getattr("position")?;
    let hv_pos = hv.getattr("position")?;
    let lx: f64 = lv_pos.get_item(0)?.extract()?;
    let ly: f64 = lv_pos.get_item(1)?.extract()?;
    let hx: f64 = hv_pos.get_item(0)?.extract()?;
    let hy: f64 = hv_pos.get_item(1)?.extract()?;
    Ok(host_math::pow(
        host_math::pow(hx - lx, 2.0) + host_math::pow(hy - ly, 2.0),
        0.5,
    ))
}

/// CPython `max(a, b)`: first-arg-wins on ties/NaN.
fn py_max(a: f64, b: f64) -> f64 {
    if b > a {
        b
    } else {
        a
    }
}

/// CPython `min(a, b)`: first-arg-wins on ties/NaN.
fn py_min(a: f64, b: f64) -> f64 {
    if b < a {
        b
    } else {
        a
    }
}

/// CPython `str.format(template, *args)` -- the only message renderer (David
/// Gay `:.1f`/`:.2f`, list reprs, everything) stays CPython.
fn py_format<'py>(
    py: Python<'py>,
    template: &str,
    args: &[Bound<'py, PyAny>],
) -> PyResult<Bound<'py, PyAny>> {
    let s = PyString::new(py, template);
    s.call_method1("format", PyTuple::new(py, args)?)
}

/// `logging.getLogger(<module>).<level>(message)`.
fn log_msg(py: Python<'_>, level: &str, msg: &Bound<'_, PyAny>) -> PyResult<()> {
    let logger = py.import("logging")?.call_method1("getLogger", (LOGGER_NAME,))?;
    logger.call_method1(level, (msg,))?;
    Ok(())
}

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

/// FFI entry for the Python shim: `run_zone_aware_slot_generation(state,
/// slot_spacing_mm, copper_zone_margin, min_routing_channel,
/// yaml_copper_zones, yaml_isolation_slots, net_class_rules)`.
#[pyfunction]
#[allow(clippy::too_many_arguments)]
#[pyo3(signature = (state, slot_spacing_mm, copper_zone_margin, min_routing_channel, yaml_copper_zones, yaml_isolation_slots, net_class_rules))]
pub fn run_zone_aware_slot_generation(
    py: Python<'_>,
    state: Py<PyAny>,
    slot_spacing_mm: f64,
    copper_zone_margin: f64,
    min_routing_channel: f64,
    yaml_copper_zones: Option<Py<PyAny>>,
    yaml_isolation_slots: Option<Py<PyAny>>,
    net_class_rules: Option<Py<PyAny>>,
) -> PyResult<Py<PyAny>> {
    let _ = min_routing_channel; // constructor config, not consumed by run()
    let rust_state = crate::d1_bridge::from_python(py, state.bind(py)).map_err(|e| {
        pyo3::exceptions::PyRuntimeError::new_err(format!("{STAGE_NAME}: {e}"))
    })?;
    let stage = ZoneAwareSlotGenerationStage {
        slot_spacing_mm,
        copper_zone_margin,
        yaml_copper_zones,
        yaml_isolation_slots,
        net_class_rules,
    };
    let out = stage.run(rust_state).map_err(|e| to_pyerr(&e))?;
    crate::d1_bridge::to_python(py, state.bind(py), &out, &["zone_slots", "reclaim_by_pin_pair"])
}
