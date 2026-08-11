// The D7 `LayerAssignmentStage` of the Rust Orchestration Engine plan
// (2026-08-09-001, Phase D batch D7): a `Stage<BoardState>` implementor
// mirroring `deterministic/stages/layer_assignment.py`.
//
// The run() orchestration moves to Rust: the `if not state.netlist` guard,
// the design-bundle `assign_layers` kernel call (net-class mapping table,
// manual-assignment branch, `or "Signal"` fallback, netlist-order
// iteration) and the `frozenset(...)` write. The `assign_layers` /
// `assign_layer_by_net_class_py` kernels and the `LayerAssignment` pyclass
// stay single-source in `temper_design_bundle_python.deterministic_leaves`
// and are driven through FFI. The Python stage instance is carried as the
// config carrier (the D4/D5/D6 pattern): `manual_assignments` and
// `net_classes` are read back off it, exactly like the oracle's
// `self.manual_assignments` / `self.net_classes`. The
// `_assign_layer_by_net_class` helper stays a directly-exercised public
// method on the Python shim.

use std::borrow::Cow;

use pyo3::prelude::*;

use crate::board_state::BoardState;
use crate::derivation_stage::stage_guard;
use crate::stage::{Stage, StageError};

const STAGE_NAME: &str = "layer_assignment";

/// The layer-assignment stage: netlist + manual/net-class config ->
/// `BoardState.layer_assignments`.
#[derive(Debug, Clone)]
pub struct LayerAssignmentStage {
    pub stage: Py<PyAny>,
}

impl Stage<BoardState> for LayerAssignmentStage {
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

impl LayerAssignmentStage {
    fn run_inner(&self, py: Python<'_>, state: BoardState) -> PyResult<BoardState> {
        let netlist = match &state.netlist {
            Some(n) if n.bind(py).is_truthy()? => n.bind(py).clone(),
            _ => return Ok(state),
        };
        let stage = self.stage.bind(py);
        let manual = stage.getattr("manual_assignments")?;
        let net_classes = stage.getattr("net_classes")?;

        // `assign_layers(state.netlist.nets, self.manual_assignments,
        // self.net_classes)` -- the design-bundle kernel.
        let leaves = py.import("temper_design_bundle_python")?.getattr("deterministic_leaves")?;
        let assignments = leaves.call_method1(
            "assign_layers",
            (netlist.getattr("nets")?, &manual, &net_classes),
        )?;

        let frozenset_ = py.import("builtins")?.getattr("frozenset")?;
        let fs = frozenset_.call1((assignments,))?;
        let mut new_state = state;
        new_state.layer_assignments = Some(fs.into_any().unbind());
        Ok(new_state)
    }
}

/// FFI entry for the Python shim: `run_layer_assignment(state, stage)`.
#[pyfunction]
pub fn run_layer_assignment(
    py: Python<'_>,
    state: Py<PyAny>,
    stage: Py<PyAny>,
) -> PyResult<Py<PyAny>> {
    let rust_state = crate::d1_bridge::from_python(py, state.bind(py)).map_err(|e| {
        pyo3::exceptions::PyRuntimeError::new_err(format!("{STAGE_NAME}: {e}"))
    })?;
    let rust_stage = LayerAssignmentStage { stage };
    let out = rust_stage
        .run(rust_state)
        .map_err(|e| crate::config_attach_stage::to_pyerr(&e))?;
    crate::d1_bridge::to_python(py, state.bind(py), &out, &["layer_assignments"])
}
