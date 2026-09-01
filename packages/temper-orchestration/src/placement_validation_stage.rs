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
// `PhasedAssignmentStage` pattern): the `_get_pin_position` /
// `_get_component_positions` / `_get_proximity_constraints` /
// `_get_signal_hv_constraints` / `_log_summary` methods stay Python for
// extraction, logging and object marshalling. The Rust stage calls the
// temper-drc-rs validation kernels directly; these paths are exercised by
// the pre-existing differential suites. The `PlacementValidationError`
// exception class stays Python (the shim raises it with the Rust-decided
// message).
//
// What stays Python / single-source (driven through FFI, bit-exact by
// construction):
// - the temper-drc-rs `validate_proximity_py` / `validate_signal_hv_py`
//   kernels and the `PlacementViolation` dataclass (the kernels are called
//   directly; the dataclass remains a Python marshalling boundary),
// - `logging` for the summary lines,
// - CPython string operations for the raise message.

#[cfg(feature = "python")]
use std::borrow::Cow;

#[cfg(feature = "python")]
use pyo3::prelude::*;
#[cfg(feature = "python")]
use pyo3::types::{PyDict, PyFloat, PyList, PyTuple};

#[cfg(feature = "python")]
use crate::board_state::BoardState;
#[cfg(feature = "python")]
use crate::d6_util;
#[cfg(feature = "python")]
use crate::derivation_stage::stage_guard;
#[cfg(feature = "python")]
use crate::stage::{Stage, StageError, StageErrorKind};
use temper_data_model::PlacementViolationList;

const STAGE_NAME: &str = "placement_validation";
const LOGGER_NAME: &str = "temper_placer.deterministic.stages.placement_validation";

#[cfg(feature = "python")]
/// The placement-validation stage: board + constraints + parsed pads ->
/// `placement_violations`, raising `PlacementValidationError` when hard-tier
/// violations are present and `fail_on_hard_violations` is set.
#[derive(Debug, Clone)]
pub struct PlacementValidationStage {
    pub stage: Py<PyAny>,
}

#[cfg(feature = "python")]
impl Stage<BoardState> for PlacementValidationStage {
    fn name(&self) -> Cow<'static, str> {
        Cow::Borrowed(STAGE_NAME)
    }

    fn run(&self, state: BoardState) -> Result<BoardState, StageError> {
        stage_guard(STAGE_NAME, || {
            Python::attach(|py| self.run_inner(py, state))
        })
    }
}

#[cfg(feature = "python")]
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
        let component_positions = PyDict::new(py);
        if let Ok(components) = board.getattr("components") {
            for comp in components.try_iter()? {
                let comp = comp?;
                let ref_: String = comp.getattr("ref")?.extract()?;
                let x: f64 = comp.getattr("x")?.extract()?;
                let y: f64 = comp.getattr("y")?.extract()?;
                let pos = PyTuple::new(
                    py,
                    [
                        PyFloat::new(py, x).into_any(),
                        PyFloat::new(py, y).into_any(),
                    ],
                )?;
                component_positions.set_item(ref_, pos)?;
            }
        }

        let violations = PyList::empty(py);
        let drc = py.import("temper_drc_rs")?;
        let proximity = stage.call_method0("_get_proximity_constraints")?;
        for constraint in proximity.try_iter()? {
            let constraint = constraint?;
            if let Some(v) = validate_proximity(py, stage, &drc, &constraint, &component_positions)?
            {
                violations.append(v)?;
            }
        }
        let signal_hv = stage.call_method0("_get_signal_hv_constraints")?;
        for constraint in signal_hv.try_iter()? {
            let constraint = constraint?;
            if let Some(v) = validate_signal_hv(py, stage, &drc, &constraint, &component_positions)?
            {
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

        let tuple = py
            .import("builtins")?
            .getattr("tuple")?
            .call1((&violations,))?;
        let mut new_state = state;
        // U6 (O-C3): the oracle's tuple construction is kept verbatim, then
        // marshalled INTO the owned `PlacementViolationList` field.
        new_state.placement_violations =
            Some(crate::marshal::to_owned::<PlacementViolationList>(&tuple)?);
        Ok(new_state)
    }
}

#[cfg(feature = "python")]
/// Resolve a pin through the Rust-owned parsed-pad kernel.  The Python stage
/// remains a configuration carrier (`parsed_pads`), but no stage method is
/// called for individual pins: all values needed by the kernel are typed at
/// this boundary and the existing `temper-drc-rs` implementation owns the
/// fallback and offset arithmetic.
fn resolve_pin_position_direct<'py>(
    _py: Python<'py>,
    drc: &Bound<'py, PyAny>,
    stage: &Bound<'py, PyAny>,
    component_ref: &Bound<'py, PyAny>,
    pin: &Bound<'py, PyAny>,
    component_positions: &Bound<'py, PyDict>,
) -> PyResult<Bound<'py, PyAny>> {
    // `resolve_pin_position_py` is the Rust-owned kernel. Calling it from
    // this Rust stage keeps the Python object only at the typed FFI boundary;
    // importantly, the Python stage's `_get_pin_position` method is never
    // consulted, so an override cannot reintroduce a compute callback.
    let parsed_pads = stage.getattr("parsed_pads")?;
    drc.call_method1(
        "resolve_pin_position_py",
        (component_ref, pin, component_positions, parsed_pads),
    )
}

#[cfg(feature = "python")]
/// Build the Python dataclass after a Rust DRC leaf has returned a violation.
/// The class remains Python-owned marshalling; validation decisions and
/// geometry stay in `temper-drc-rs`.
#[allow(clippy::too_many_arguments)]
fn make_placement_violation<'py>(
    py: Python<'py>,
    constraint: &Bound<'py, PyAny>,
    violation_type: &str,
    severity: &Bound<'py, PyAny>,
    message: &Bound<'py, PyAny>,
    actual: Option<&Bound<'py, PyAny>>,
    required: Option<&Bound<'py, PyAny>>,
    component_a: Option<&str>,
    component_b: Option<&str>,
) -> PyResult<Bound<'py, PyAny>> {
    let kwargs = PyDict::new(py);
    kwargs.set_item("constraint_name", constraint.getattr("name")?)?;
    kwargs.set_item("violation_type", violation_type)?;
    kwargs.set_item("message", message)?;
    kwargs.set_item("severity", severity)?;
    if let Some(value) = component_a
        && !value.is_empty()
    {
        kwargs.set_item("component_a", value)?;
    }
    if let Some(value) = component_b
        && !value.is_empty()
    {
        kwargs.set_item("component_b", value)?;
    }
    if let Some(value) = actual {
        kwargs.set_item("actual_distance_mm", value)?;
    }
    if let Some(value) = required {
        kwargs.set_item("required_distance_mm", value)?;
    }
    py.import("temper_placer.deterministic.stages.placement_validation")?
        .getattr("PlacementViolation")?
        .call((), Some(&kwargs))
}

#[cfg(feature = "python")]
fn validate_proximity<'py>(
    py: Python<'py>,
    stage: &Bound<'py, PyAny>,
    drc: &Bound<'py, PyAny>,
    constraint: &Bound<'py, PyAny>,
    component_positions: &Bound<'py, PyDict>,
) -> PyResult<Option<Bound<'py, PyAny>>> {
    let from_pos = resolve_pin_position_direct(
        py,
        drc,
        stage,
        &constraint.getattr("from_component")?,
        &constraint.getattr("from_pin")?,
        component_positions,
    )?;
    let to_pos = resolve_pin_position_direct(
        py,
        drc,
        stage,
        &constraint.getattr("to_component")?,
        &constraint.getattr("to_pin")?,
        component_positions,
    )?;
    let result = drc.call_method1("validate_proximity_py", (constraint, &from_pos, &to_pos))?;
    if result.is_none() || !result.get_item(0)?.extract::<bool>()? {
        return Ok(None);
    }
    let severity = result.get_item(1)?;
    let actual = result.get_item(2)?;
    let required = result.get_item(3)?;
    let message = result.get_item(4)?;
    let component_a: String = result.get_item(5)?.extract()?;
    let component_b: String = result.get_item(6)?.extract()?;
    let missing =
        severity.extract::<String>()? == "warning" && (from_pos.is_none() || to_pos.is_none());
    let kind = if missing {
        "missing_component"
    } else {
        "proximity"
    };
    Ok(Some(make_placement_violation(
        py,
        constraint,
        kind,
        &severity,
        &message,
        if missing { None } else { Some(&actual) },
        if missing { None } else { Some(&required) },
        Some(&component_a),
        Some(&component_b),
    )?))
}

#[cfg(feature = "python")]
fn validate_signal_hv<'py>(
    py: Python<'py>,
    stage: &Bound<'py, PyAny>,
    drc: &Bound<'py, PyAny>,
    constraint: &Bound<'py, PyAny>,
    component_positions: &Bound<'py, PyDict>,
) -> PyResult<Option<Bound<'py, PyAny>>> {
    let signal_pos = resolve_pin_position_direct(
        py,
        drc,
        stage,
        &constraint.getattr("signal_component")?,
        &constraint.getattr("signal_pin")?,
        component_positions,
    )?;
    let target_pos = resolve_pin_position_direct(
        py,
        drc,
        stage,
        &constraint.getattr("target_component")?,
        &constraint.getattr("target_pin")?,
        component_positions,
    )?;
    let hv_positions = PyList::empty(py);
    for hv_pin in constraint.getattr("hv_pins")?.try_iter()? {
        let hv_pin = hv_pin?;
        let hv_pos = resolve_pin_position_direct(
            py,
            drc,
            stage,
            &constraint.getattr("hv_component")?,
            &hv_pin,
            component_positions,
        )?;
        if !hv_pos.is_none() {
            hv_positions.append((hv_pin, hv_pos))?;
        }
    }
    let result = drc.call_method1(
        "validate_signal_hv_py",
        (constraint, &signal_pos, &target_pos, &hv_positions),
    )?;
    if result.is_none() || !result.get_item(0)?.extract::<bool>()? {
        return Ok(None);
    }
    let severity = result.get_item(1)?;
    let actual = result.get_item(2)?;
    let required = result.get_item(3)?;
    let message = result.get_item(4)?;
    let component_a: String = result.get_item(5)?.extract()?;
    let component_b: String = result.get_item(6)?.extract()?;
    let kind: String = result.get_item(7)?.extract()?;
    let missing = kind == "missing_component";
    Ok(Some(make_placement_violation(
        py,
        constraint,
        &kind,
        &severity,
        &message,
        if missing { None } else { Some(&actual) },
        if missing { None } else { Some(&required) },
        if missing { None } else { Some(&component_a) },
        if missing { None } else { Some(&component_b) },
    )?))
}

#[cfg(feature = "python")]
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

#[cfg(feature = "python")]
/// FFI entry for the Python shim: `run_placement_validation(state, stage)` ->
/// `(state, message)`.
#[pyfunction]
pub fn run_placement_validation(
    py: Python<'_>,
    state: Py<PyAny>,
    stage: Py<PyAny>,
) -> PyResult<(Py<PyAny>, Option<String>)> {
    let rust_state = crate::d1_bridge::from_python(py, state.bind(py))
        .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(format!("{STAGE_NAME}: {e}")))?;
    let rust_stage = PlacementValidationStage { stage };
    let result = rust_stage.run(rust_state);
    crate::d6_util::write_back_or_raise(py, state.bind(py), result, &["placement_violations"])
}
