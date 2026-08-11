// The D1 `ConfigAttachStage` of the Rust Orchestration Engine plan
// (2026-08-09-001, Phase D batch D1): a pure pass-through stage mirroring
// `deterministic/stages/config_attach.py`.
//
// The stage copies a parsed `PlacementConstraints` config object onto
// `BoardState.config` so downstream stages (HvLvPartitionStage in
// particular) can read their own block from `state.config`. The Python
// `run` guarded on `hasattr(state, "with_config")` -- a dead branch, since
// BoardState always has `with_config`; the Rust form keeps only the
// observable behavior: config present AND `state.config` None -> set it,
// otherwise the state is returned unchanged (identity preserved).

#[cfg(feature = "python")]
use std::borrow::Cow;

#[cfg(feature = "python")]
use pyo3::prelude::*;

#[cfg(feature = "python")]
use crate::board_state::BoardState;
#[cfg(feature = "python")]
use crate::derivation_stage::stage_guard;
#[cfg(feature = "python")]
use crate::stage::{Stage, StageError};

#[cfg(feature = "python")]
/// The config pass-through stage: raw config -> `BoardState.config`.
#[derive(Debug, Clone)]
pub struct ConfigAttachStage {
    pub config: Option<Py<PyAny>>,
}

#[cfg(feature = "python")]
impl Stage<BoardState> for ConfigAttachStage {
    fn name(&self) -> Cow<'static, str> {
        Cow::Borrowed("config_attach")
    }

    fn run(&self, state: BoardState) -> Result<BoardState, StageError> {
        stage_guard("config_attach", || {
            Python::attach(|py| {
                let mut new_state = state.clone();
                if let Some(config) = &self.config
                    && new_state.config.is_none()
                {
                    new_state.config = Some(config.clone_ref(py));
                }
                Ok(new_state)
            })
        })
    }
}

#[cfg(feature = "python")]
/// FFI entry for the Python shim: `run_config_attach(state, config)`.
#[pyfunction]
#[pyo3(signature = (state, config))]
pub fn run_config_attach(
    py: Python<'_>,
    state: Py<PyAny>,
    config: Option<Py<PyAny>>,
) -> PyResult<Py<PyAny>> {
    let rust_state = crate::d1_bridge::from_python(py, state.bind(py)).map_err(|e| {
        pyo3::exceptions::PyRuntimeError::new_err(format!("config_attach: {e}"))
    })?;
    let stage = ConfigAttachStage {
        config: config.clone(),
    };
    let out = stage.run(rust_state).map_err(|e| to_pyerr(&e))?;
    crate::d1_bridge::to_python(py, state.bind(py), &out, &["config"])
}

#[cfg(feature = "python")]
pub(crate) fn to_pyerr(e: &StageError) -> PyErr {
    pyo3::exceptions::PyRuntimeError::new_err(e.message.clone())
}
