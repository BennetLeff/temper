// The D7 `ApplyPlacementsStage` of the Rust Orchestration Engine plan
// (2026-08-09-001, Phase D batch D7): a `Stage<BoardState>` implementor
// mirroring `deterministic/stages/apply_placements.py`.
//
// This stage is pure orchestration (no design-bundle leaf kernel): it reads
// `state.netlist` + `state.placements`, and rewrites every placed
// component's `initial_position` via `dataclasses.replace`, rebuilds the
// netlist, and writes `netlist` back. The `dataclasses.replace` calls on the
// pyclass objects (Component / Netlist) go through the Python `dataclasses`
// module via FFI -- exactly the operation the oracle performs -- so the
// pyclass field copying is bit-exact by construction. The guard path
// (`not state.netlist or not state.placements`) returns the ORIGINAL state
// (identity preserved); the write-back in `d1_bridge.rs` compares the new
// netlist against the original so an unchanged stage is never rewritten.

#[cfg(feature = "python")]
use std::borrow::Cow;

#[cfg(feature = "python")]
use pyo3::prelude::*;
#[cfg(feature = "python")]
use pyo3::types::{PyDict, PyList};

#[cfg(feature = "python")]
use crate::board_state::BoardState;
#[cfg(feature = "python")]
use crate::derivation_stage::stage_guard;
#[cfg(feature = "python")]
use crate::stage::{Stage, StageError};

#[cfg(feature = "python")]
use temper_design_bundle::Netlist;

/// The apply-placements stage: netlist + placements -> netlist with
/// `initial_position` synced from the placements frozenset.
#[derive(Debug, Clone, Default)]
pub struct ApplyPlacementsStage;

#[cfg(feature = "python")]
impl Stage<BoardState> for ApplyPlacementsStage {
    fn name(&self) -> Cow<'static, str> {
        Cow::Borrowed("apply_placements")
    }

    fn run(&self, state: BoardState) -> Result<BoardState, StageError> {
        stage_guard("apply_placements", || {
            Python::attach(|py| {
                let to_stage = |e: pyo3::PyErr| crate::derivation_stage::pyerr_stage("apply_placements", e);
                self.run_inner(py, state).map_err(to_stage)
            })
        })
    }
}

#[cfg(feature = "python")]
impl ApplyPlacementsStage {
    fn run_inner(&self, py: Python<'_>, state: BoardState) -> PyResult<BoardState> {
        // `if not state.netlist or not state.placements: return state`.
        let netlist = match &state.netlist {
            Some(n) if n.bind(py).is_truthy()? => n.bind(py).clone(),
            _ => return Ok(state),
        };
        let placements = match &state.placements {
            Some(p) if p.bind(py).is_truthy()? => p.bind(py).clone(),
            _ => return Ok(state),
        };

        // `placements_dict = dict(state.placements)` -- built through the
        // builtins `dict()` over the ORIGINAL frozenset so the dict keys are
        // the original ref objects (string `in` semantics preserved).
        let placements_dict: Py<PyDict> = py
            .import("builtins")?
            .getattr("dict")?
            .call1((placements,))?
            .extract()?;
        let placements_dict = placements_dict.bind(py);

        // `dataclasses.replace` is the ONLY reconstruction primitive.
        let replace = py.import("dataclasses")?.getattr("replace")?;

        let updated_components = PyList::empty(py);
        for component in netlist.getattr("components")?.try_iter()? {
            let component = component?;
            let ref_ = component.getattr("ref")?;
            if placements_dict.contains(&ref_)? {
                let pos = placements_dict.get_item(&ref_)?;
                let kwargs = PyDict::new(py);
                kwargs.set_item("initial_position", pos)?;
                let new_comp = replace.call((&component,), Some(&kwargs))?;
                updated_components.append(new_comp)?;
            } else {
                updated_components.append(&component)?;
            }
        }

        // `new_netlist = replace(state.netlist, components=list(...))`.
        let nl_kwargs = PyDict::new(py);
        nl_kwargs.set_item("components", &updated_components)?;
        let new_netlist = replace.call((&netlist,), Some(&nl_kwargs))?;

        let mut new_state = state;
        new_state.netlist = Some(new_netlist.extract::<Py<Netlist>>()?);
        Ok(new_state)
    }
}

#[cfg(feature = "python")]
/// FFI entry for the Python shim: `run_apply_placements(state)`.
#[pyfunction]
pub fn run_apply_placements(
    py: Python<'_>,
    state: Py<PyAny>,
) -> PyResult<Py<PyAny>> {
    let rust_state = crate::d1_bridge::from_python(py, state.bind(py)).map_err(|e| {
        pyo3::exceptions::PyRuntimeError::new_err(format!("apply_placements: {e}"))
    })?;
    let stage = ApplyPlacementsStage;
    let out = stage.run(rust_state).map_err(|e| crate::config_attach_stage::to_pyerr(&e))?;
    crate::d1_bridge::to_python(py, state.bind(py), &out, &["netlist"])
}
