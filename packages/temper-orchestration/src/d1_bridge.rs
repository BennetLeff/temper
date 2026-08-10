// D1 bridge: the Python-BoardState <-> Rust-BoardState conversion seam for
// the deterministic setup stages (Rust Orchestration Engine plan
// 2026-08-09-001, Phase D batch D1).
//
// The three D1 stages (`ConfigAttachStage`, `NetOrderingStage`,
// `DrcOracleSetupStage` + `NetClassSetupStage`) are `Stage<BoardState>`
// implementors operating on the Rust phased `BoardState`. Their Python
// shims (`deterministic/stages/{config_attach,net_ordering,setup}.py`) stay
// thin: `run(state)` crosses the FFI once per stage through a pyfunction,
// which builds the Rust `BoardState` from the Python dataclass here, runs
// the stage, and writes only the changed fields back via
// `dataclasses.replace`.
//
// The conversion is a pure Py<PyAny> pass-through (D2: fields are NOT
// tightened speculatively); the only owned field is `net_order`
// (tuple[str, ...] <-> Vec<String>).
//
// Write-back semantics: `to_python` writes a candidate field back only when
// the stage actually changed it (compared against the ORIGINAL Python
// state), so an unchanged stage returns the original Python state object
// unchanged (identity preserved -- matching the Python stages' `return
// state` paths). A field whose Rust value is `None` is never written back.

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyTuple};

use crate::board_state::BoardState;

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
    bs.drc_violations = attr_opt(state, "drc_violations")?;
    bs.design_rules = attr_opt(state, "design_rules")?;
    bs.connectivity_violations = attr_opt(state, "connectivity_violations")?;
    bs.placement_violations = attr_opt(state, "placement_violations")?;
    bs.placements = attr_opt(state, "placements")?;
    bs.used_slots = attr_opt(state, "used_slots")?;
    bs.config = attr_opt(state, "config")?;
    bs.component_domain_map = attr_opt(state, "component_domain_map")?;
    bs.routing_corridors = attr_opt(state, "routing_corridors")?;
    bs.domain_regions = attr_opt(state, "domain_regions")?;
    bs.routes = attr_opt(state, "routes")?;
    bs.vias = attr_opt(state, "vias")?;
    bs.violations = attr_opt(state, "violations")?;
    bs.zones = attr_opt(state, "zones")?;
    bs.component_zone_map = attr_opt(state, "component_zone_map")?;
    bs.zone_slots = attr_opt(state, "zone_slots")?;
    bs.layer_assignments = attr_opt(state, "layer_assignments")?;
    bs.net_order = state.getattr("net_order")?.extract::<Vec<String>>()?;
    Ok(bs)
}

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
            "net_order" => {
                let orig_tuple = orig.getattr("net_order")?;
                let orig_vec: Vec<String> = orig_tuple.extract()?;
                orig_vec != out.net_order
            }
            other => {
                return Err(PyValueError::new_err(format!(
                    "d1 write-back does not know field {other:?}"
                )))
            }
        };
        if !changed {
            continue;
        }
        let value: Py<PyAny> = match *name {
            "config" => out
                .config
                .clone()
                .ok_or_else(|| PyValueError::new_err("config field is None on write-back"))?,
            "drc_oracle" => out
                .drc_oracle
                .clone()
                .ok_or_else(|| PyValueError::new_err("drc_oracle field is None on write-back"))?,
            "net_order" => PyTuple::new(py, out.net_order.iter().map(|s| s.as_str()))?
                .into_any()
                .unbind(),
            other => {
                return Err(PyValueError::new_err(format!(
                    "d1 write-back does not know field {other:?}"
                )))
            }
        };
        kwargs.set_item(*name, value)?;
    }
    if kwargs.is_empty() {
        return Ok(orig.clone().unbind());
    }
    Ok(replace.call((orig,), Some(&kwargs))?.unbind())
}

fn attr_opt(state: &Bound<'_, PyAny>, name: &str) -> PyResult<Option<Py<PyAny>>> {
    let value = state.getattr(name)?;
    if value.is_none() {
        Ok(None)
    } else {
        Ok(Some(value.unbind()))
    }
}

/// Whether the Rust output value for an `Option<Py>` field differs from the
/// original Python attribute value. `None` in either position counts as
/// different (a stage populating a previously-empty field must write it).
fn py_opt_changed(
    orig: &Bound<'_, PyAny>,
    out: &BoardState,
    name: &str,
) -> PyResult<bool> {
    let orig_val = orig.getattr(name)?;
    let out_val: Option<&Py<PyAny>> = match name {
        "config" => out.config.as_ref(),
        "drc_oracle" => out.drc_oracle.as_ref(),
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
