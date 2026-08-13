// The D2 `ZoneAssignmentStage` of the Rust Orchestration Engine plan
// (2026-08-09-001, Phase D batch D2): a `Stage<BoardState>` implementor
// mirroring `deterministic/stages/zone_assignment.py`.
//
// The stage reads `BoardState.netlist`, delegates the assignment compute to
// the already-Rust leaf kernel
// (`temper_design_bundle_python.deterministic_stages.assign_component_zones`
// — the Phase-5 first-slice migration), rebuilds the dict exactly like the
// oracle's `dict(pairs)` (insertion order preserved), and writes
// `frozenset(dict.items())` into `BoardState.component_zone_map`. The
// `state.netlist` guard returns the state unchanged (identity preserved).

#[cfg(feature = "python")]
use std::borrow::Cow;

#[cfg(feature = "python")]
use pyo3::prelude::*;
#[cfg(feature = "python")]
use pyo3::types::PyDict;

#[cfg(feature = "python")]
use crate::board_state::BoardState;
#[cfg(feature = "python")]
use crate::config_attach_stage::to_pyerr;
#[cfg(feature = "python")]
use crate::derivation_stage::{pyerr_stage, stage_guard};
#[cfg(feature = "python")]
use crate::stage::{Stage, StageError};
use temper_data_model::StrPairSet;

/// The zone-assignment stage: netlist -> `component_zone_map` (frozenset of
/// `(ref, zone)` pairs).
#[derive(Debug, Clone)]
pub struct ZoneAssignmentStage;

#[cfg(feature = "python")]
impl Stage<BoardState> for ZoneAssignmentStage {
    fn name(&self) -> Cow<'static, str> {
        Cow::Borrowed("zone_assignment")
    }

    fn run(&self, state: BoardState) -> Result<BoardState, StageError> {
        stage_guard("zone_assignment", || {
            Python::attach(|py| {
                let to_stage = |e: pyo3::PyErr| pyerr_stage("zone_assignment", e);
                let netlist = match &state.netlist {
                    Some(n) if n.bind(py).is_truthy().map_err(to_stage)? => n.clone_ref(py),
                    _ => return Ok(state),
                };
                let tdb = py
                    .import("temper_design_bundle_python")
                    .map_err(to_stage)?
                    .getattr("deterministic_stages")
                    .map_err(to_stage)?;
                let pairs = tdb
                    .call_method1("assign_component_zones", (netlist,))
                    .map_err(to_stage)?;
                let pairs: Vec<(String, String)> = pairs.extract().map_err(to_stage)?;

                // `dict(pairs)` then `frozenset(dict.items())` -- the dict
                // is rebuilt so insertion order and dedup semantics match
                // the oracle's expression order exactly.
                let d = PyDict::new(py);
                for (r, z) in pairs {
                    d.set_item(r, z).map_err(to_stage)?;
                }
                let items = d.call_method0("items").map_err(to_stage)?;
                let frozenset = py
                    .import("builtins")
                    .map_err(to_stage)?
                    .getattr("frozenset")
                    .map_err(to_stage)?
                    .call1((items,))
                    .map_err(to_stage)?;

                                let mut new_state = state;
                // U6 (O-C3) group-2: `frozenset(dict.items())` is kept
                // verbatim, then marshalled INTO the owned `StrPairSet` field.
                new_state.component_zone_map = Some(
                    crate::marshal::to_owned::<StrPairSet>(&frozenset).map_err(to_stage)?,
                );
                Ok(new_state)
            })
        })
    }
}

#[cfg(feature = "python")]
/// FFI entry for the Python shim: `run_zone_assignment(state)`.
#[pyfunction]
pub fn run_zone_assignment(
    py: Python<'_>,
    state: Py<PyAny>,
) -> PyResult<Py<PyAny>> {
    let rust_state = crate::d1_bridge::from_python(py, state.bind(py)).map_err(|e| {
        pyo3::exceptions::PyRuntimeError::new_err(format!("zone_assignment: {e}"))
    })?;
    let stage = ZoneAssignmentStage;
    let out = stage.run(rust_state).map_err(|e| to_pyerr(&e))?;
    crate::d1_bridge::to_python(py, state.bind(py), &out, &["component_zone_map"])
}
