// The D7 `PowerPlaneStage` of the Rust Orchestration Engine plan
// (2026-08-09-001, Phase D batch D7): a `Stage<BoardState>` implementor
// mirroring `deterministic/stages/power_plane.py`.
//
// The run() orchestration moves to Rust: the `if not state.netlist` guard,
// the existing-assignment `list(...)` conversion, the netlist net-name
// collection, the design-bundle `recompute_plane_assignments` kernel call
// (the existing-upgrade / new-plane-nets / remaining-nets three-pass
// reassignment with the `plane_layers.get(net_name, 1)` default) and the
// `frozenset(...)` write. The kernel stays single-source in
// `temper_design_bundle_python.deterministic_leaves` and is driven through
// FFI. The Python stage instance is the config carrier (the D4/D5/D6
// pattern): `plane_nets` / `plane_layers` (defaulted in the constructor to
// the module tables `TEMPER_PLANE_NETS` / `TEMPER_PLANE_LAYERS`) are read
// back off it.

#[cfg(feature = "python")]
use std::borrow::Cow;

#[cfg(feature = "python")]
use pyo3::prelude::*;
#[cfg(feature = "python")]
use pyo3::types::PyList;

#[cfg(feature = "python")]
use crate::board_state::BoardState;
#[cfg(feature = "python")]
use crate::derivation_stage::stage_guard;
#[cfg(feature = "python")]
use crate::stage::{Stage, StageError};
#[cfg(feature = "python")]
use temper_data_model::LayerAssignmentSet;

const STAGE_NAME: &str = "power_plane";

#[cfg(feature = "python")]
/// The power-plane stage: netlist + layer_assignments -> plane-marked
/// `BoardState.layer_assignments`.
#[derive(Debug, Clone)]
pub struct PowerPlaneStage {
    pub stage: Py<PyAny>,
}

#[cfg(feature = "python")]
impl Stage<BoardState> for PowerPlaneStage {
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
impl PowerPlaneStage {
    fn run_inner(&self, py: Python<'_>, state: BoardState) -> PyResult<BoardState> {
        let netlist = match &state.netlist {
            Some(n) if n.bind(py).is_truthy()? => n.bind(py).clone(),
            _ => return Ok(state),
        };
        let stage = self.stage.bind(py);
        let plane_nets = stage.getattr("plane_nets")?;
        let plane_layers = stage.getattr("plane_layers")?;

        // `existing_assignments = list(state.layer_assignments) if
        // state.layer_assignments else []`.
        // U6 (O-C3) group-2: the owned `LayerAssignmentSet` is rebuilt into
        // the Python frozenset, then `list(...)`-ed exactly like the oracle.
        let existing = match &state.layer_assignments {
            Some(la) if !la.is_empty() => {
                let fs = crate::marshal::to_python::<LayerAssignmentSet>(py, la)?;
                py.import("builtins")?.getattr("list")?.call1((fs,))?
            }
            _ => PyList::empty(py).into_any(),
        };

        // `all_nets = [net.name for net in state.netlist.nets]`.
        let all_nets = PyList::empty(py);
        for net in netlist.getattr("nets")?.try_iter()? {
            let net = net?;
            all_nets.append(net.getattr("name")?)?;
        }

        // `recompute_plane_assignments(existing, plane_nets, plane_layers,
        // all_nets)` -- the design-bundle kernel.
        let leaves = py
            .import("temper_design_bundle_python")?
            .getattr("deterministic_leaves")?;
        let new_assignments = leaves.call_method1(
            "recompute_plane_assignments",
            (&existing, &plane_nets, &plane_layers, &all_nets),
        )?;

        let frozenset_ = py.import("builtins")?.getattr("frozenset")?;
        let fs = frozenset_.call1((new_assignments,))?;
        let mut new_state = state;
        new_state.layer_assignments = Some(crate::marshal::to_owned::<LayerAssignmentSet>(&fs)?);
        Ok(new_state)
    }
}

#[cfg(feature = "python")]
/// FFI entry for the Python shim: `run_power_plane(state, stage)`.
#[pyfunction]
pub fn run_power_plane(py: Python<'_>, state: Py<PyAny>, stage: Py<PyAny>) -> PyResult<Py<PyAny>> {
    let rust_state = crate::d1_bridge::from_python(py, state.bind(py))
        .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(format!("{STAGE_NAME}: {e}")))?;
    let rust_stage = PowerPlaneStage { stage };
    let out = rust_stage
        .run(rust_state)
        .map_err(|e| crate::config_attach_stage::to_pyerr(&e))?;
    crate::d1_bridge::to_python(py, state.bind(py), &out, &["layer_assignments"])
}
