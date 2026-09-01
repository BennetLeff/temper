// The D2 `ZoneAssignmentStage` of the Rust Orchestration Engine plan
// (2026-08-09-001, Phase D batch D2): a `Stage<BoardState>` implementor
// mirroring `deterministic/stages/zone_assignment.py`.
//
// The stage reads `BoardState.netlist`, marshals its dynamic pyclass surface
// once, and delegates assignment to the pyo3-free data-model kernel.  This
// keeps Python as an object-adaptation boundary while avoiding the former
// Rust -> Python -> Rust callback through the design-bundle leaf module.
// Results are written as the owned `StrPairSet`, which the bridge marshals to
// the oracle's `frozenset(dict.items())` representation. The `state.netlist`
// guard returns the state unchanged (identity preserved).

#[cfg(feature = "python")]
use std::borrow::Cow;

#[cfg(feature = "python")]
use pyo3::exceptions::{PyAttributeError, PyTypeError, PyValueError};
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
use temper_data_model::StrPairSet;

#[cfg(feature = "python")]
fn unpack_pin_pair<'py>(pin: &Bound<'py, PyAny>) -> PyResult<(String, String)> {
    let mut iter = pin.try_iter().map_err(|_| {
        PyTypeError::new_err(format!(
            "cannot unpack non-iterable {} object",
            pin.get_type()
                .name()
                .map(|name| name.to_string())
                .unwrap_or_else(|_| "object".to_string())
        ))
    })?;
    let first = iter.next().ok_or_else(|| {
        PyValueError::new_err("not enough values to unpack (expected 2, got 0)")
    })??;
    let second = iter.next().ok_or_else(|| {
        PyValueError::new_err("not enough values to unpack (expected 2, got 1)")
    })??;
    if iter.next().is_some() {
        return Err(PyValueError::new_err(
            "too many values to unpack (expected 2)",
        ));
    }
    Ok((first.extract()?, second.extract()?))
}

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
                let netlist = netlist.bind(py);
                let nets = netlist.getattr("nets").map_err(to_stage)?;
                let components = netlist.getattr("components").map_err(to_stage)?;

                // Marshal only the attributes consumed by the pure kernel.
                // AttributeError for a missing net_class has the same
                // default-as-Signal behavior as the historical leaf; other
                // exceptions remain loud.
                let mut marshalled_nets = Vec::new();
                for net in nets.try_iter().map_err(to_stage)? {
                    let net = net.map_err(to_stage)?;
                    let name: String = net
                        .getattr("name")
                        .map_err(to_stage)?
                        .extract()
                        .map_err(to_stage)?;
                    let net_class: Option<String> = match net.getattr("net_class") {
                        Ok(value) => value.extract().map_err(to_stage)?,
                        Err(err) if err.is_instance_of::<PyAttributeError>(py) => None,
                        Err(err) => return Err(to_stage(err)),
                    };
                    let pins = net.getattr("pins").map_err(to_stage)?;
                    let mut marshalled_pins = Vec::new();
                    for pin in pins.try_iter().map_err(to_stage)? {
                        let pin = pin.map_err(to_stage)?;
                        let (component_ref, pin_name) = unpack_pin_pair(&pin).map_err(to_stage)?;
                        marshalled_pins.push((component_ref, pin_name));
                    }
                    marshalled_nets.push((name, net_class, marshalled_pins));
                }
                let mut component_refs = Vec::new();
                for component in components.try_iter().map_err(to_stage)? {
                    let component = component.map_err(to_stage)?;
                    component_refs.push(
                        component
                            .getattr("ref")
                            .map_err(to_stage)?
                            .extract::<String>()
                            .map_err(to_stage)?,
                    );
                }
                let pairs = temper_data_model::zone_assignment::assign_component_zones(
                    &component_refs,
                    &marshalled_nets,
                );

                let mut new_state = state;
                new_state.component_zone_map = Some(StrPairSet(pairs.into_iter().collect()));
                Ok(new_state)
            })
        })
    }
}

#[cfg(feature = "python")]
/// FFI entry for the Python shim: `run_zone_assignment(state)`.
#[pyfunction]
pub fn run_zone_assignment(py: Python<'_>, state: Py<PyAny>) -> PyResult<Py<PyAny>> {
    let rust_state = crate::d1_bridge::from_python(py, state.bind(py))
        .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(format!("zone_assignment: {e}")))?;
    let stage = ZoneAssignmentStage;
    let out = stage.run(rust_state).map_err(|e| to_pyerr(&e))?;
    crate::d1_bridge::to_python(py, state.bind(py), &out, &["component_zone_map"])
}
