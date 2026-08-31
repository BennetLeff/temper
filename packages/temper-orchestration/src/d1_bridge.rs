// D1 bridge: the Python-BoardState <-> Rust-BoardState conversion seam for
// the deterministic setup stages (Rust Orchestration Engine plan
// 2026-08-09-001, Phase D batch D1).
//
// The three D1 stages (`ConfigAttachStage`, `NetOrderingStage`,
// `DrcOracleSetupStage` + `NetClassSetupStage`) are `Stage<BoardState>`
// implementors operating on the Rust phased `BoardState`. Their Python
// shims were collapsed onto the generic `RustFunctionStage` adapter
// (shim-debt cleanup 2026-08-20: `deterministic/stages/{net_ordering,
// setup}.py` deleted; `config_attach.py` kept only as an import-path
// re-export for the pinned pipeline oracle): `run(state)` crosses the FFI
// once per stage through a pyfunction, which builds the Rust `BoardState`
// from the Python dataclass here, runs the stage, and writes only the
// changed fields back via `dataclasses.replace`.
//
// The conversion is a pure Py<PyAny> pass-through (D2: fields are NOT
// tightened speculatively); the owned fields are `net_order`
// (tuple[str, ...] <-> Vec<String>) and, since unit O-C3/U1, `used_slots`
// (frozenset of (x, y) tuples <-> HashSet<SlotId>) read/written through
// `crate::marshal`.
//
// Write-back semantics: `to_python` writes a candidate field back only when
// the stage actually changed it (compared against the ORIGINAL Python
// state), so an unchanged stage returns the original Python state object
// unchanged (identity preserved -- matching the Python stages' `return
// state` paths). A field whose Rust value is `None` is never written back.

#[cfg(feature = "python")]
use pyo3::exceptions::PyValueError;
#[cfg(feature = "python")]
use pyo3::prelude::*;
#[cfg(feature = "python")]
use pyo3::types::{PyDict, PyTuple};

#[cfg(feature = "python")]
use std::collections::HashSet;

#[cfg(feature = "python")]
use temper_data_model::{
    ConnectivityViolationList, LayerAssignmentSet, PlacementSet, PlacementViolationList,
    StrPairSet, ViolationList, ZoneSet, ZoneSlotsSet,
};

#[cfg(feature = "python")]
use crate::board_state::{BoardState, RouteEntry, SlotId, ViaEntry};

#[cfg(feature = "python")]
/// Read the Python BoardState attributes the D1 stages consume into a Rust
/// `BoardState`. Python `None` maps to Rust `None`; a non-None value
/// (including a non-empty default like `placements=frozenset()`) maps to
/// `Some(Py)`.
pub(crate) fn from_python(_py: Python<'_>, state: &Bound<'_, PyAny>) -> PyResult<BoardState> {
    let mut bs = BoardState::new();
    bs.board = attr_opt(state, "board")?;
    bs.netlist = attr_opt(state, "netlist")?;
    bs.loops = attr_opt(state, "loops")?;
    bs.grid = attr_opt(state, "grid")?;
    bs.drc_oracle = attr_opt(state, "drc_oracle")?;
    // U6 (O-C3): the three validation-result fields read through the boundary
    // marshaller (the U1 used_slots pattern). `Option<T>`'s `Marshal` impl
    // maps Python `None` → Rust `None` and a non-empty `tuple` to the owned
    // `*List` `Vec` newtype (a list is REJECTED — the contract is a tuple).
    bs.drc_violations =
        crate::marshal::to_owned::<Option<ViolationList>>(&state.getattr("drc_violations")?)?;
    bs.design_rules = attr_opt(state, "design_rules")?;
    bs.connectivity_violations = crate::marshal::to_owned::<Option<ConnectivityViolationList>>(
        &state.getattr("connectivity_violations")?,
    )?;
    bs.placement_violations = crate::marshal::to_owned::<Option<PlacementViolationList>>(
        &state.getattr("placement_violations")?,
    )?;
    // U6 (O-C3) group-2: the six remaining COLLECTION fields read through the
    // boundary marshaller (the U1 used_slots pattern). `Option<T>`'s `Marshal`
    // impl maps Python `None` → Rust `None` and a `frozenset` of the element
    // type to the owned `*Set` `HashSet` newtype (a list is REJECTED — the
    // contract is a frozenset).
    bs.placements =
        crate::marshal::to_owned::<Option<PlacementSet>>(&state.getattr("placements")?)?;
    // U1 (O-C3): the first field read through the boundary marshaller
    // instead of `attr_opt`. `Option<T>`'s `Marshal` impl maps Python `None`
    // to Rust `None` and a `frozenset` of `(x, y)` tuples to
    // `Some(HashSet<SlotId>)`; the concrete `frozenset` type and every float
    // leaf are validated here at the boundary (a shape change is a LOUD
    // `PyTypeError`, not a downstream silent mismatch).
    bs.used_slots =
        crate::marshal::to_owned::<Option<HashSet<SlotId>>>(&state.getattr("used_slots")?)?;
    bs.config = attr_opt(state, "config")?;
    bs.component_domain_map = attr_opt(state, "component_domain_map")?;
    bs.routing_corridors = attr_opt(state, "routing_corridors")?;
    bs.domain_regions = attr_opt(state, "domain_regions")?;
    bs.routes = crate::marshal::to_owned::<Option<HashSet<RouteEntry>>>(&state.getattr("routes")?)?;
    bs.vias = crate::marshal::to_owned::<Option<HashSet<ViaEntry>>>(&state.getattr("vias")?)?;
    bs.violations = attr_opt(state, "violations")?;
    bs.zones = crate::marshal::to_owned::<Option<ZoneSet>>(&state.getattr("zones")?)?;
    bs.component_zone_map =
        crate::marshal::to_owned::<Option<StrPairSet>>(&state.getattr("component_zone_map")?)?;
    bs.zone_slots =
        crate::marshal::to_owned::<Option<ZoneSlotsSet>>(&state.getattr("zone_slots")?)?;
    bs.layer_assignments = crate::marshal::to_owned::<Option<LayerAssignmentSet>>(
        &state.getattr("layer_assignments")?,
    )?;
    bs.reclaim_by_pin_pair = attr_opt(state, "reclaim_by_pin_pair")?;
    bs.net_order = state.getattr("net_order")?.extract::<Vec<String>>()?;
    Ok(bs)
}

#[cfg(feature = "python")]
/// Write the changed candidate fields of a Rust `BoardState` back onto the
/// Python BoardState via `dataclasses.replace(state, **kwargs)`. Each
/// candidate field is written back ONLY if the original Python value differs
/// from the Rust output value (a stage that left a field untouched does not
/// rewrite it). When no candidate field changed, the ORIGINAL Python state
/// object is returned unchanged (identity preserved).
pub(crate) fn to_python(
    py: Python<'_>,
    orig: &Bound<'_, PyAny>,
    out: &BoardState,
    candidates: &[&str],
) -> PyResult<Py<PyAny>> {
    let replace = py.import("dataclasses")?.getattr("replace")?;
    let kwargs = PyDict::new(py);
    for name in candidates {
        let changed = match *name {
            "config" => py_opt_changed(orig, out, "config")?,
            "drc_oracle" => py_opt_changed(orig, out, "drc_oracle")?,
            "grid" => grid_changed(orig, out)?,
            // U6 (O-C3) group-2: the six remaining collection fields are
            // owned — the change test marshals the ORIGINAL Python value to
            // the same owned type and compares (the shared generic helper).
            "zones" => owned_opt_changed::<ZoneSet>(orig, "zones", &out.zones)?,
            "component_zone_map" => owned_opt_changed::<StrPairSet>(
                orig,
                "component_zone_map",
                &out.component_zone_map,
            )?,
            "zone_slots" => owned_opt_changed::<ZoneSlotsSet>(orig, "zone_slots", &out.zone_slots)?,
            "placements" => owned_opt_changed::<PlacementSet>(orig, "placements", &out.placements)?,
            // U1 (O-C3): the first typed candidate — the change test
            // marshals the ORIGINAL Python value to the same owned type and
            // compares (see `used_slots_changed`); the write-back value goes
            // through `marshal::to_python`, which always produces a
            // `frozenset` (the dataclass field contract).
            "used_slots" => used_slots_changed(orig, out)?,
            "design_rules" => py_opt_changed(orig, out, "design_rules")?,
            "reclaim_by_pin_pair" => py_opt_changed(orig, out, "reclaim_by_pin_pair")?,
            // D6 (validation stages): the validation-result and geometry
            // fields the D6 stages write back.
            "routes" => owned_opt_changed::<HashSet<RouteEntry>>(orig, "routes", &out.routes)?,
            "vias" => owned_opt_changed::<HashSet<ViaEntry>>(orig, "vias", &out.vias)?,
            // U6 (O-C3): the violation lists are owned — the change test
            // marshals the ORIGINAL Python value to the same owned type and
            // compares (the U1 pattern, via the shared generic helper).
            "drc_violations" => {
                owned_opt_changed::<ViolationList>(orig, "drc_violations", &out.drc_violations)?
            }
            "placement_violations" => owned_opt_changed::<PlacementViolationList>(
                orig,
                "placement_violations",
                &out.placement_violations,
            )?,
            "connectivity_violations" => owned_opt_changed::<ConnectivityViolationList>(
                orig,
                "connectivity_violations",
                &out.connectivity_violations,
            )?,
            // D7 (routing-adjacent stages): the domain/assignment/netlist
            // fields the D7 stages write back.
            "layer_assignments" => owned_opt_changed::<LayerAssignmentSet>(
                orig,
                "layer_assignments",
                &out.layer_assignments,
            )?,
            "netlist" => py_opt_changed(orig, out, "netlist")?,
            "component_domain_map" => py_opt_changed(orig, out, "component_domain_map")?,
            "routing_corridors" => py_opt_changed(orig, out, "routing_corridors")?,
            "domain_regions" => py_opt_changed(orig, out, "domain_regions")?,
            "net_order" => {
                let orig_tuple = orig.getattr("net_order")?;
                let orig_vec: Vec<String> = orig_tuple.extract()?;
                orig_vec != out.net_order
            }
            other => {
                return Err(PyValueError::new_err(format!(
                    "d1 write-back does not know field {other:?}"
                )));
            }
        };
        if !changed {
            continue;
        }
        let value: Py<PyAny> = match *name {
            "config" => opt_value(py, &out.config),
            "drc_oracle" => opt_value(py, &out.drc_oracle),
            "grid" => opt_value(py, &out.grid),
            "zones" => crate::marshal::to_python::<Option<ZoneSet>>(py, &out.zones)?,
            "component_zone_map" => {
                crate::marshal::to_python::<Option<StrPairSet>>(py, &out.component_zone_map)?
            }
            "zone_slots" => crate::marshal::to_python::<Option<ZoneSlotsSet>>(py, &out.zone_slots)?,
            "placements" => crate::marshal::to_python::<Option<PlacementSet>>(py, &out.placements)?,
            "used_slots" => {
                crate::marshal::to_python::<Option<HashSet<SlotId>>>(py, &out.used_slots)?
            }
            "design_rules" => opt_value(py, &out.design_rules),
            "reclaim_by_pin_pair" => opt_value(py, &out.reclaim_by_pin_pair),
            "routes" => crate::marshal::to_python::<Option<HashSet<RouteEntry>>>(py, &out.routes)?,
            "vias" => crate::marshal::to_python::<Option<HashSet<ViaEntry>>>(py, &out.vias)?,
            "drc_violations" => {
                crate::marshal::to_python::<Option<ViolationList>>(py, &out.drc_violations)?
            }
            "placement_violations" => crate::marshal::to_python::<Option<PlacementViolationList>>(
                py,
                &out.placement_violations,
            )?,
            "connectivity_violations" => crate::marshal::to_python::<
                Option<ConnectivityViolationList>,
            >(py, &out.connectivity_violations)?,
            "layer_assignments" => {
                crate::marshal::to_python::<Option<LayerAssignmentSet>>(py, &out.layer_assignments)?
            }
            "netlist" => opt_value(py, &out.netlist),
            "component_domain_map" => opt_value(py, &out.component_domain_map),
            "routing_corridors" => opt_value(py, &out.routing_corridors),
            "domain_regions" => opt_value(py, &out.domain_regions),
            "net_order" => PyTuple::new(py, out.net_order.iter().map(|s| s.as_str()))?
                .into_any()
                .unbind(),
            other => {
                return Err(PyValueError::new_err(format!(
                    "d1 write-back does not know field {other:?}"
                )));
            }
        };
        kwargs.set_item(*name, value)?;
    }
    if kwargs.is_empty() {
        return Ok(orig.clone().unbind());
    }
    Ok(replace.call((orig,), Some(&kwargs))?.unbind())
}

#[cfg(feature = "python")]
fn attr_opt(state: &Bound<'_, PyAny>, name: &str) -> PyResult<Option<Py<PyAny>>> {
    let value = state.getattr(name)?;
    if value.is_none() {
        Ok(None)
    } else {
        Ok(Some(value.unbind()))
    }
}

#[cfg(feature = "python")]
/// The Python value to write back for an `Option<Py>` field: the value
/// itself, or Python `None` when the stage cleared the field (a changed
/// field -- original Some -> Rust None -- writes an explicit None, matching
/// the Python stage's `dataclasses.replace(field=None)`).
fn opt_value(py: Python<'_>, opt: &Option<Py<PyAny>>) -> Py<PyAny> {
    match opt {
        Some(v) => v.clone(),
        None => py.None(),
    }
}

#[cfg(feature = "python")]
/// Whether the Rust output value for an `Option<Py>` field differs from the
/// original Python attribute value. `None` in either position counts as
/// different (a stage populating a previously-empty field must write it).
fn py_opt_changed(orig: &Bound<'_, PyAny>, out: &BoardState, name: &str) -> PyResult<bool> {
    let orig_val = orig.getattr(name)?;
    let out_val: Option<&Py<PyAny>> = match name {
        "config" => out.config.as_ref(),
        "drc_oracle" => out.drc_oracle.as_ref(),
        "design_rules" => out.design_rules.as_ref(),
        "reclaim_by_pin_pair" => out.reclaim_by_pin_pair.as_ref(),
        "netlist" => out.netlist.as_ref(),
        "component_domain_map" => out.component_domain_map.as_ref(),
        "routing_corridors" => out.routing_corridors.as_ref(),
        "domain_regions" => out.domain_regions.as_ref(),
        _ => return Ok(false),
    };
    match (orig_val.is_none(), out_val) {
        (true, Some(_)) => Ok(true),
        (false, None) => Ok(true),
        (false, Some(v)) => {
            let same = v.bind(orig.py()).eq(&orig_val)?;
            Ok(!same)
        }
        (true, None) => Ok(false),
    }
}

#[cfg(feature = "python")]
/// The `used_slots` write-back test for an OWNED field (the U1 rewire
/// pattern): marshal the ORIGINAL Python attribute to the same owned type
/// the Rust field holds and compare with Rust equality. This preserves the
/// `dataclasses.replace` semantics — a changed field writes the new value,
/// an unchanged field keeps the original Python object (identity preserved,
/// matching the Python stages' `return state` paths) — without ever holding
/// a `Py<PyAny>` copy of the field.
fn used_slots_changed(orig: &Bound<'_, PyAny>, out: &BoardState) -> PyResult<bool> {
    let orig_owned =
        crate::marshal::to_owned::<Option<HashSet<SlotId>>>(&orig.getattr("used_slots")?)?;
    Ok(orig_owned != out.used_slots)
}

#[cfg(feature = "python")]
/// The generic OWNED write-back test (the U6 extension of the U1
/// `used_slots_changed` pattern): marshal the ORIGINAL Python attribute to the
/// same owned type the Rust field holds and compare with Rust equality. This
/// preserves the `dataclasses.replace` semantics — a changed field writes the
/// new value, an unchanged field keeps the original Python object (identity
/// preserved) — without ever holding a `Py<PyAny>` copy of the field.
fn owned_opt_changed<T: crate::marshal::Marshal + PartialEq>(
    orig: &Bound<'_, PyAny>,
    name: &str,
    out_val: &Option<T>,
) -> PyResult<bool> {
    let orig_owned = crate::marshal::to_owned::<Option<T>>(&orig.getattr(name)?)?;
    Ok(orig_owned != *out_val)
}

#[cfg(feature = "python")]
/// The `grid` write-back test: the stage either produces a NEW `ClearanceGrid`
/// object (write it back) or returns the state unchanged on the no-board
/// guard (leave it). Dataclass `==` cannot be used here -- `ClearanceGrid`
/// `@dataclass` equality compares only the four constructor dimensions, so a
/// fresh grid with equal dims (same board + cell size) would wrongly be
/// skipped. Identity is the oracle-faithful signal.
fn grid_changed(orig: &Bound<'_, PyAny>, out: &BoardState) -> PyResult<bool> {
    let orig_val = orig.getattr("grid")?;
    match (orig_val.is_none(), &out.grid) {
        (true, Some(_)) => Ok(true),
        (false, None) => Ok(true),
        (false, Some(v)) => {
            let same = v.bind(orig.py()).is(&orig_val);
            Ok(!same)
        }
        (true, None) => Ok(false),
    }
}
