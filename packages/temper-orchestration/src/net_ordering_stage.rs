// The D1 `NetOrderingStage` of the Rust Orchestration Engine plan
// (2026-08-09-001, Phase D batch D1): a `Stage<BoardState>` implementor
// mirroring `deterministic/stages/net_ordering.py`.
//
// The stage reads `BoardState.netlist` and `BoardState.loops`, builds an
// empty `LoopCollection` when `loops` is absent, delegates the ordering
// compute to the already-Rust `temper_rust_router.order_nets_py` kernel via
// the `router_v6.net_ordering.order_nets` marshalling shim (the wire
// marshalling of the Netlist/LoopCollection pyclasses is genuinely Python
// glue; the ordering decision itself is the Rust kernel), and writes the
// resulting order back into `BoardState.net_order`.

#[cfg(feature = "python")]
use std::borrow::Cow;

#[cfg(feature = "python")]
use pyo3::prelude::*;

#[cfg(feature = "python")]
use crate::board_state::BoardState;
#[cfg(feature = "python")]
use crate::config_attach_stage::to_pyerr;
#[cfg(feature = "python")]
use crate::derivation_stage::{pyerr_stage, stage_guard};
#[cfg(feature = "python")]
use crate::stage::{Stage, StageError};

#[cfg(feature = "python")]
/// The net-ordering stage: netlist + loops -> `net_order`.
#[derive(Debug, Clone)]
pub struct NetOrderingStage {
    pub net_priority: Option<Py<PyAny>>,
}

#[cfg(feature = "python")]
impl Stage<BoardState> for NetOrderingStage {
    fn name(&self) -> Cow<'static, str> {
        Cow::Borrowed("net_ordering")
    }

    fn run(&self, state: BoardState) -> Result<BoardState, StageError> {
        stage_guard("net_ordering", || {
            Python::attach(|py| {
                let netlist = match &state.netlist {
                    Some(n) => n.clone_ref(py),
                    None => return Ok(state),
                };
                // loops = state.loops or LoopCollection()
                let loops: Py<PyAny> = match &state.loops {
                    Some(l) => l.clone_ref(py),
                    None => {
                        let loop_collection = py
                            .import("temper_placer.core.loop")
                            .map_err(|e| pyerr_stage("net_ordering", e))?
                            .getattr("LoopCollection")
                            .map_err(|e| pyerr_stage("net_ordering", e))?;
                        loop_collection
                            .call0()
                            .map_err(|e| pyerr_stage("net_ordering", e))?
                            .into_any()
                            .unbind()
                    }
                };
                let order_nets = py
                    .import("temper_placer.router_v6.net_ordering")
                    .map_err(|e| pyerr_stage("net_ordering", e))?
                    .getattr("order_nets")
                    .map_err(|e| pyerr_stage("net_ordering", e))?;
                let net_priority = self.net_priority.as_ref().map(|p| p.clone_ref(py));
                let ordered = order_nets
                    .call1((netlist, loops, net_priority))
                    .map_err(|e| pyerr_stage("net_ordering", e))?;
                let ordered: Vec<String> = ordered
                    .extract()
                    .map_err(|e| pyerr_stage("net_ordering", e))?;
                let mut new_state = state;
                new_state.net_order = ordered;
                Ok(new_state)
            })
        })
    }
}

#[cfg(feature = "python")]
/// FFI entry for the Python shim: `run_net_ordering(state, net_priority)`.
#[pyfunction]
#[pyo3(signature = (state, net_priority=None))]
pub fn run_net_ordering(
    py: Python<'_>,
    state: Py<PyAny>,
    net_priority: Option<Py<PyAny>>,
) -> PyResult<Py<PyAny>> {
    let rust_state = crate::d1_bridge::from_python(py, state.bind(py))
        .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(format!("net_ordering: {e}")))?;
    let stage = NetOrderingStage { net_priority };
    let out = stage.run(rust_state).map_err(|e| to_pyerr(&e))?;
    crate::d1_bridge::to_python(py, state.bind(py), &out, &["net_order"])
}
