// The D6 `DRCValidationStage` of the Rust Orchestration Engine plan
// (2026-08-09-001, Phase D batch D6): a `Stage<BoardState>` implementor
// mirroring `deterministic/stages/drc_validation.py`.
//
// The whole run() orchestration moves to Rust: the no-oracle guard, the
// `drc_oracle.validate_all()` call, the `_log_summary` (through the
// temper-drc-rs `summarize_violations_py` kernel), the `threshold_decision_py`
// raise decision and the `drc_violations=tuple(violations)` write. The
// DRCValidationError exception class stays Python (the shim raises it with the
// Rust-decided message).
//
// What stays Python / single-source (driven through FFI, bit-exact by
// construction):
// - the `DRCOracle.validate_all()` call-back (the router_v6 oracle surface),
// - the `threshold_decision_py` / `summarize_violations_py` leaf kernels in
//   temper-drc-rs (the raise decision + count-by-type sorting),
// - `logging` for the summary lines.
//
// The raise contract: the Rust stage's run() returns
// `Err(StageError { kind: Infeasible, message })` when the oracle decision is
// to raise -- the Python `run()` raises DRCValidationError before
// `dataclasses.replace`, so nothing is written back on that path. The shared
// `write_back_or_raise` channel hands the message to the shim, which raises
// its module's `DRCValidationError`.

#[cfg(feature = "python")]
use std::borrow::Cow;

#[cfg(feature = "python")]
use pyo3::prelude::*;
#[cfg(feature = "python")]
use pyo3::types::PyList;

#[cfg(feature = "python")]
use crate::board_state::BoardState;
#[cfg(feature = "python")]
use crate::d6_util;
#[cfg(feature = "python")]
use crate::derivation_stage::stage_guard;
#[cfg(feature = "python")]
use crate::stage::{Stage, StageError, StageErrorKind};

const STAGE_NAME: &str = "drc_validation";
const LOGGER_NAME: &str = "temper_placer.deterministic.stages.drc_validation";

/// The post-routing DRC validation stage: oracle -> `drc_violations` (tuple),
/// raising `DRCValidationError` when configured thresholds are exceeded.
#[derive(Debug, Clone)]
pub struct DRCValidationStage {
    pub fail_on_violations: bool,
    pub max_violations: i64,
}

#[cfg(feature = "python")]
impl Stage<BoardState> for DRCValidationStage {
    fn name(&self) -> Cow<'static, str> {
        Cow::Borrowed(STAGE_NAME)
    }

    fn run(&self, state: BoardState) -> Result<BoardState, StageError> {
        stage_guard(STAGE_NAME, || Python::attach(|py| self.run_inner(py, state)))
    }
}

#[cfg(feature = "python")]
impl DRCValidationStage {
    fn run_inner(&self, py: Python<'_>, state: BoardState) -> Result<BoardState, StageError> {
        let oracle = match &state.drc_oracle {
            Some(o) if o.bind(py).is_truthy()? => o.bind(py).clone(),
            _ => {
                // `logger.warning("No DRCOracle in state, skipping DRC validation")`
                d6_util::log_msg(
                    py,
                    LOGGER_NAME,
                    "warning",
                    &pyo3::types::PyString::new(py, "No DRCOracle in state, skipping DRC validation").into_any(),
                )?;
                return Ok(state);
            }
        };

        let violations = oracle.call_method0("validate_all")?;
        self.log_summary(py, &violations)?;

        let drc = py.import("temper_drc_rs")?;
        let should_raise: bool;
        let message: String;
        (should_raise, message) = drc
            .call_method1(
                "threshold_decision_py",
                (self.fail_on_violations, self.max_violations, violations.len()?),
            )?
            .extract()?;
        if should_raise {
            return Err(StageError::new(
                STAGE_NAME,
                message,
                StageErrorKind::Infeasible,
            ));
        }

        let tuple = py.import("builtins")?.getattr("tuple")?.call1((&violations,))?;
        let mut new_state = state;
        new_state.drc_violations = Some(tuple.into_any().unbind());
        Ok(new_state)
    }

    /// `_log_summary`: the count-by-type summary via the temper-drc-rs kernel.
    fn log_summary(&self, py: Python<'_>, violations: &Bound<'_, PyAny>) -> PyResult<()> {
        if violations.len()? == 0 {
            d6_util::log_msg(
                py,
                LOGGER_NAME,
                "info",
                &"DRC validation passed: 0 violations".into_pyobject(py)?.into_any(),
            )?;
            return Ok(());
        }
        let drc = py.import("temper_drc_rs")?;
        let summary = drc.call_method1("summarize_violations_py", (violations,))?;
        let total: usize = summary.get_item(0)?.extract()?;
        let by_type: Bound<'_, PyAny> = summary.get_item(1)?;
        let msg = d6_util::py_format(
            py,
            "DRC validation: {} violations",
            &[total.into_pyobject(py)?.into_any()],
        )?;
        d6_util::log_msg(py, LOGGER_NAME, "warning", &msg)?;
        let rows: Bound<'_, PyList> = by_type.cast_into()?;
        for row in rows.try_iter()? {
            let row = row?;
            let vtype = row.get_item(0)?;
            let count = row.get_item(1)?;
            let msg = d6_util::py_format(
                py,
                "  {}: {}",
                &[vtype.into_any(), count.into_any()],
            )?;
            d6_util::log_msg(py, LOGGER_NAME, "warning", &msg)?;
        }
        Ok(())
    }
}

#[cfg(feature = "python")]
/// FFI entry for the Python shim: `run_drc_validation(state,
/// fail_on_violations, max_violations)` -> `(state, message)`.
#[pyfunction]
pub fn run_drc_validation(
    py: Python<'_>,
    state: Py<PyAny>,
    fail_on_violations: bool,
    max_violations: i64,
) -> PyResult<(Py<PyAny>, Option<String>)> {
    let rust_state = crate::d1_bridge::from_python(py, state.bind(py)).map_err(|e| {
        pyo3::exceptions::PyRuntimeError::new_err(format!("{STAGE_NAME}: {e}"))
    })?;
    let stage = DRCValidationStage {
        fail_on_violations,
        max_violations,
    };
    let result = stage.run(rust_state);
    crate::d6_util::write_back_or_raise(py, state.bind(py), result, &["drc_violations"])
}
