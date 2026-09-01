// The D2 `SlotGenerationStage` of the Rust Orchestration Engine plan
// (2026-08-09-001, Phase D batch D2): a `Stage<BoardState>` implementor
// mirroring `deterministic/stages/slot_generation.py`.
//
// The stage reads `BoardState.zones`, iterates the frozenset of Zone
// objects, delegates the slot-grid walk to the already-Rust leaf kernel
// (`temper_design_bundle_python.deterministic_stages.generate_slots_for_zone`
// — the Phase-5 first-slice migration), stores each zone as
// `(zone.name, tuple(slots))`, and writes `frozenset(zone_slots_list)` into
// `BoardState.zone_slots`. The `state.zones` guard reproduces the Python
// truthiness test (`if not state.zones`) and returns the state unchanged
// (identity preserved) — an absent zone OR an empty `frozenset()` (the
// BoardState default) skips the stage exactly like the oracle, so a
// pre-populated `zone_slots` is never clobbered by the empty-zones path.
//
// The slot coordinates come out of the kernel with their exact accumulated
// `+=` drift; `tuple(slots)` is called on the kernel's returned list so the
// result tuple has exactly the kernel's values (builtin tuple, not a Rust
// re-wrap).

#[cfg(feature = "python")]
use std::borrow::Cow;

#[cfg(feature = "python")]
use pyo3::prelude::*;
#[cfg(feature = "python")]
use pyo3::types::{PyList, PyTuple};

#[cfg(feature = "python")]
use crate::board_state::BoardState;
#[cfg(feature = "python")]
use crate::config_attach_stage::to_pyerr;
#[cfg(feature = "python")]
use crate::derivation_stage::{pyerr_stage, stage_guard};
#[cfg(feature = "python")]
use crate::stage::{Stage, StageError};

#[cfg(feature = "python")]
use temper_data_model::{ZoneSet, ZoneSlotsSet};

/// The slot-generation stage: zones -> `zone_slots` (frozenset of
/// `(zone_name, tuple_of_slots)` entries).
#[derive(Debug, Clone)]
pub struct SlotGenerationStage {
    pub slot_spacing_mm: f64,
}

#[cfg(feature = "python")]
impl Stage<BoardState> for SlotGenerationStage {
    fn name(&self) -> Cow<'static, str> {
        Cow::Borrowed("slot_generation")
    }

    fn run(&self, state: BoardState) -> Result<BoardState, StageError> {
        stage_guard("slot_generation", || {
            Python::attach(|py| {
                let to_stage = |e: pyo3::PyErr| pyerr_stage("slot_generation", e);
                // U6 (O-C3) group-2: the zones guard (`if not state.zones`)
                // maps to `!set.is_empty()`; the owned `ZoneSet` is rebuilt
                // into the Python frozenset the iteration expects.
                let zones = match &state.zones {
                    Some(z) if !z.is_empty() => {
                        crate::marshal::to_python::<ZoneSet>(py, z).map_err(to_stage)?
                    }
                    _ => return Ok(state),
                };
                let tdb = py
                    .import("temper_design_bundle_python")
                    .map_err(to_stage)?
                    .getattr("deterministic_stages")
                    .map_err(to_stage)?;
                let builtins = py.import("builtins").map_err(to_stage)?;

                let zone_slots_fs = generate_all_zone_slots(
                    py,
                    zones.bind(py),
                    &tdb,
                    &builtins,
                    self.slot_spacing_mm,
                )
                .map_err(to_stage)?;

                let mut new_state = state;
                // U6 (O-C3) group-2: the oracle's `frozenset(zone_slots_list)`
                // is kept verbatim, then marshalled INTO the owned
                // `ZoneSlotsSet` field.
                new_state.zone_slots = Some(
                    crate::marshal::to_owned::<ZoneSlotsSet>(zone_slots_fs.bind(py))
                        .map_err(to_stage)?,
                );
                Ok(new_state)
            })
        })
    }
}

// ---------------------------------------------------------------------------
// Slot-grid generation
// ---------------------------------------------------------------------------

#[cfg(feature = "python")]
/// The `for zone in state.zones` loop body: each zone's bounds are unpacked
/// (`(x_min, y_min), (x_max, y_max)`), the kernel generates the slots, the
/// per-zone entry `(zone.name, tuple(slots))` is appended, and the whole
/// list is wrapped in a `frozenset` like the oracle's
/// `frozenset(zone_slots_list)`.
fn generate_all_zone_slots<'py>(
    py: Python<'py>,
    zones: &Bound<'py, PyAny>,
    tdb: &Bound<'py, PyAny>,
    builtins: &Bound<'py, PyAny>,
    spacing: f64,
) -> PyResult<Py<PyAny>> {
    let zone_slots_list = PyList::empty(py);
    for zone in zones.try_iter()? {
        let zone = zone?;
        // `(x_min, y_min), (x_max, y_max) = zone.bounds`
        let bounds = zone.getattr("bounds")?;
        let lo = bounds.get_item(0)?;
        let hi = bounds.get_item(1)?;
        let x_min: f64 = lo.get_item(0)?.extract()?;
        let y_min: f64 = lo.get_item(1)?.extract()?;
        let x_max: f64 = hi.get_item(0)?.extract()?;
        let y_max: f64 = hi.get_item(1)?.extract()?;
        let slots = tdb.call_method1(
            "generate_slots_for_zone",
            (x_min, y_min, x_max, y_max, spacing),
        )?;
        // `tuple(slots)` -- builtin tuple over the kernel's list of
        // (x, y) tuples.
        let slot_tuple = builtins.getattr("tuple")?.call1((slots,))?;
        // `(zone.name, tuple(slots))`
        let entry = PyTuple::new(py, [zone.getattr("name")?, slot_tuple])?;
        zone_slots_list.append(entry)?;
    }
    let frozenset = builtins.getattr("frozenset")?.call1((zone_slots_list,))?;
    Ok(frozenset.into_any().unbind())
}

#[cfg(feature = "python")]
/// FFI entry for the Python shim: `run_slot_generation(state,
/// slot_spacing_mm)`.
#[pyfunction]
#[pyo3(signature = (state, slot_spacing_mm=5.0))]
pub fn run_slot_generation(
    py: Python<'_>,
    state: Py<PyAny>,
    slot_spacing_mm: f64,
) -> PyResult<Py<PyAny>> {
    let rust_state = crate::d1_bridge::from_python(py, state.bind(py))
        .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(format!("slot_generation: {e}")))?;
    let stage = SlotGenerationStage { slot_spacing_mm };
    let out = stage.run(rust_state).map_err(|e| to_pyerr(&e))?;
    crate::d1_bridge::to_python(py, state.bind(py), &out, &["zone_slots"])
}
