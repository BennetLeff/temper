// The D6 `PlacementValidationStage` of the Rust Orchestration Engine plan
// (2026-08-09-001, Phase D batch D6): a `Stage<BoardState>` implementor
// mirroring `deterministic/stages/placement_validation.py`.
//
// The run() orchestration moves to Rust: the no-board guard, the
// component-position extraction call-back, the proximity + signal-HV
// constraint sweeps, the violation collection, the `_log_summary` call-back,
// the hard-violation filter, the `PlacementValidationError` raise decision +
// message text and the `placement_violations=tuple(...)` write. The Python
// stage instance is carried as the config carrier (the D4/D5
// `PhasedAssignmentStage` pattern): the per-constraint validation helpers
// `_validate_proximity` / `_validate_signal_hv` (and the `_get_pin_position` /
// `_get_component_positions` / `_get_proximity_constraints` /
// `_get_signal_hv_constraints` / `_log_summary` methods they drive) stay
// Python single-source and are CALLED BACK on the stage -- they are directly
// exercised by the pre-existing suites (`test_drc_leaf_rust_differential.py`),
// the established D5 mixin-helper boundary. The `PlacementValidationError`
// exception class stays Python (the shim raises it with the Rust-decided
// message).
//
// What stays Python / single-source (driven through FFI, bit-exact by
// construction):
// - the temper-drc-rs `validate_proximity_py` / `validate_signal_hv_py`
//   kernels and the `PlacementViolation` dataclass (both reached through the
//   called-back helper methods),
// - `logging` for the summary lines,
// - CPython string operations for the raise message.

use std::borrow::Cow;

use pyo3::prelude::*;
use pyo3::types::PyList;

use crate::board_state::BoardState;
use crate::d6_util;
use crate::derivation_stage::stage_guard;
use crate::stage::{Stage, StageError, StageErrorKind};

const STAGE_NAME: &str = "placement_validation";
const LOGGER_NAME: &str = "temper_placer.deterministic.stages.placement_validation";

/// The placement-validation stage: board + constraints + parsed pads ->
/// `placement_violations`, raising `PlacementValidationError` when hard-tier
/// violations are present and `fail_on_hard_violations` is set.
#[derive(Debug, Clone)]
pub struct PlacementValidationStage {
    pub stage: Py<PyAny>,
}

impl Stage<BoardState> for PlacementValidationStage {
    fn name(&self) -> Cow<'static, str> {
        Cow::Borrowed(STAGE_NAME)
    }

    fn run(&self, state: BoardState) -> Result<BoardState, StageError> {
        stage_guard(STAGE_NAME, || Python::attach(|py| self.run_inner(py, state)))
    }
}

impl PlacementValidationStage {
    fn run_inner(&self, py: Python<'_>, state: BoardState) -> Result<BoardState, StageError> {
        let board = match &state.board {
            Some(b) if b.bind(py).is_truthy()? => b.bind(py).clone(),
            _ => {
                // `logger.warning("No board in state, skipping placement validation")`
                d6_util::log_msg(
                    py,
                    LOGGER_NAME,
                    "warning",
                    &pyo3::types::PyString::new(
                        py,
                        "No board in state, skipping placement validation",
                    )
                    .into_any(),
                )?;
                return Ok(state);
            }
        };

        let stage = self.stage.bind(py);

        // `component_positions = self._get_component_positions(state)` -- the
        // {ref: (x, y)} dict, built here from board.components (the method
        // stays on the Python stage as directly-exercised public API; the
        // differential pins the two agree).
        let component_positions = pyo3::types::PyDict::new(py);
        if let Ok(components) = board.getattr("components") {
            for comp in components.try_iter()? {
                let comp = comp?;
                let pos = pyo3::types::PyTuple::new(
                    py,
                    [comp.getattr("x")?.into_any(), comp.getattr("y")?.into_any()],
                )?;
                component_positions.set_item(comp.getattr("ref")?, pos)?;
            }
        }

        let violations = PyList::empty(py);
        let proximity = stage.call_method0("_get_proximity_constraints")?;
        for constraint in proximity.try_iter()? {
            let constraint = constraint?;
            let v = stage.call_method1("_validate_proximity", (&constraint, &component_positions))?;
            if !v.is_none() {
                violations.append(v)?;
            }
        }
        let signal_hv = stage.call_method0("_get_signal_hv_constraints")?;
        for constraint in signal_hv.try_iter()? {
            let constraint = constraint?;
            let v = stage.call_method1("_validate_signal_hv", (&constraint, &component_positions))?;
            if !v.is_none() {
                violations.append(v)?;
            }
        }

        stage.call_method1("_log_summary", (&violations,))?;

        // hard_violations = [v for v in violations if v.severity == "error"]
        let hard = PyList::empty(py);
        for v in violations.try_iter()? {
            let v = v?;
            let severity: String = v.getattr("severity")?.str()?.to_string();
            if severity == "error" {
                hard.append(&v)?;
            }
        }
        let fail_on_hard_violations: bool = stage.getattr("fail_on_hard_violations")?.extract()?;
        if fail_on_hard_violations && hard.len() > 0 {
            let message = build_raise_message(py, &hard)?;
            return Err(StageError::new(
                STAGE_NAME,
                message,
                StageErrorKind::Infeasible,
            ));
        }

        let tuple = py.import("builtins")?.getattr("tuple")?.call1((&violations,))?;
        let mut new_state = state;
        new_state.placement_violations = Some(tuple.into_any().unbind());
        Ok(new_state)
    }
}

/// `f"{len(hard)} hard placement violations found:\n" + "\n".join(...)` --
/// rendered through CPython string operations (`str.format`, `+`, `join`).
fn build_raise_message(py: Python<'_>, hard: &Bound<'_, PyAny>) -> PyResult<String> {
    let head = d6_util::py_format(
        py,
        "{} hard placement violations found:\n",
        &[hard.len()?.into_pyobject(py)?.into_any()],
    )?;
    let parts = PyList::empty(py);
    for v in hard.try_iter()? {
        let v = v?;
        let prefix = pyo3::types::PyString::new(py, "  - ");
        let line = prefix.add(v.getattr("message")?)?;
        parts.append(line)?;
    }
    let joined = pyo3::types::PyString::new(py, "\n").call_method1("join", (&parts,))?;
    let full = head.add(&joined)?;
    full.str()?.extract()
}

/// FFI entry for the Python shim: `run_placement_validation(state, stage)` ->
/// `(state, message)`.
#[pyfunction]
pub fn run_placement_validation(
    py: Python<'_>,
    state: Py<PyAny>,
    stage: Py<PyAny>,
) -> PyResult<(Py<PyAny>, Option<String>)> {
    let rust_state = crate::d1_bridge::from_python(py, state.bind(py)).map_err(|e| {
        pyo3::exceptions::PyRuntimeError::new_err(format!("{STAGE_NAME}: {e}"))
    })?;
    let rust_stage = PlacementValidationStage { stage };
    let result = rust_stage.run(rust_state);
    crate::d6_util::write_back_or_raise(py, state.bind(py), result, &["placement_violations"])
}
