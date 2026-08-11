// The D6 `CourtyardCheckStage` of the Rust Orchestration Engine plan
// (2026-08-09-001, Phase D batch D6): a `Stage<BoardState>` implementor
// mirroring `deterministic/stages/courtyard_check.py`.
//
// The whole run() orchestration moves to Rust: the no-placements guard, the
// iterative nudge loop (the `dist < 1e-6` coincident-centers branch, the
// libm-`pow` `** 0.5` distance, the `_clamp_position` call-backs, the
// `frozenset(placements.items())` write) and the `print` messages. The
// Python stage instance is carried as the config carrier (the D4/D5
// `PhasedAssignmentStage` pattern): `_find_collisions` and `_clamp_position`
// are CALLED BACK on it, and `max_iterations` / `nudge_step` are read from it.
//
// What stays Python / single-source (driven through FFI, bit-exact by
// construction):
// - the shapely/GEOS STRtree `_find_collisions` collision detection (a
//   geometry-engine library boundary, not bit-reproducible by any Rust port),
// - the CPython `random.random()` nudge noise (seeded identically per arm in
//   the differential; the two trajectories consume the identical sequence),
// - the temper-drc-rs `_clamp_position` kernel,
// - `print` / `str.format` for every interpolated message.

#[cfg(feature = "python")]
use std::borrow::Cow;

#[cfg(feature = "python")]
use pyo3::prelude::*;
#[cfg(feature = "python")]
use pyo3::types::PyTuple;

#[cfg(feature = "python")]
use crate::board_state::BoardState;
#[cfg(feature = "python")]
use crate::d6_util;
#[cfg(feature = "python")]
use crate::derivation_stage::{pyerr_stage, stage_guard};
#[cfg(feature = "python")]
use crate::host_math;
#[cfg(feature = "python")]
use crate::stage::{Stage, StageError};

const STAGE_NAME: &str = "courtyard_check";

#[cfg(feature = "python")]
/// The courtyard-overlap resolution stage: `placements` -> `placements`
/// (overlapping courtyards nudged apart and clamped to the board bounds).
#[derive(Debug, Clone)]
pub struct CourtyardCheckStage {
    pub stage: Py<PyAny>,
}

#[cfg(feature = "python")]
impl Stage<BoardState> for CourtyardCheckStage {
    fn name(&self) -> Cow<'static, str> {
        Cow::Borrowed(STAGE_NAME)
    }

    fn run(&self, state: BoardState) -> Result<BoardState, StageError> {
        stage_guard(STAGE_NAME, || {
            Python::attach(|py| {
                let to_stage = |e: pyo3::PyErr| pyerr_stage(STAGE_NAME, e);
                self.run_inner(py, state).map_err(to_stage)
            })
        })
    }
}

#[cfg(feature = "python")]
impl CourtyardCheckStage {
    fn run_inner(&self, py: Python<'_>, state: BoardState) -> PyResult<BoardState> {
        let placements = match &state.placements {
            Some(p) if p.bind(py).is_truthy()? => p.bind(py).clone(),
            _ => return Ok(state),
        };
        let stage = self.stage.bind(py);
        let max_iterations: i64 = stage.getattr("max_iterations")?.extract()?;
        let nudge_step: f64 = stage.getattr("nudge_step")?.extract()?;
        let find_collisions = stage.getattr("_find_collisions")?;
        let clamp_position = stage.getattr("_clamp_position")?;
        let random_fn = py.import("random")?.getattr("random")?;
        let builtins = py.import("builtins")?;

        // `placements = dict(state.placements)` (mutable working copy).
        let placements_dict = builtins.getattr("dict")?.call1((&placements,))?;
        // `list(placements.keys())` -- the oracle's discarded no-op list.
        let _ = builtins
            .getattr("list")?
            .call1((placements_dict.call_method0("keys")?,))?;

        for i in 0..max_iterations {
            let collisions = find_collisions.call1((&placements_dict,))?;
            if collisions.len()? > 0 {
                let msg = d6_util::py_format(
                    py,
                    "DEBUG: CourtyardCheck Iteration {}: Found {} overlapping pairs",
                    &[
                        i.into_pyobject(py)?.into_any(),
                        collisions.len()?.into_pyobject(py)?.into_any(),
                    ],
                )?;
                d6_util::py_print(py, &[msg])?;
            }
            for pair in collisions.try_iter()? {
                let pair = pair?;
                let ref1 = pair.get_item(0)?;
                let ref2 = pair.get_item(1)?;
                let pos1 = placements_dict.get_item(&ref1)?;
                let pos2 = placements_dict.get_item(&ref2)?;

                let mut dx = pos2.get_item(0)?.extract::<f64>()? - pos1.get_item(0)?.extract::<f64>()?;
                let mut dy = pos2.get_item(1)?.extract::<f64>()? - pos1.get_item(1)?.extract::<f64>()?;
                // `dist = (dx**2 + dy**2) ** 0.5` -- libm pow, NOT sqrt.
                let mut dist = host_math::pow(
                    host_math::pow(dx, 2.0) + host_math::pow(dy, 2.0),
                    0.5,
                );
                if dist < 1e-6 {
                    dx = 1.0;
                    dy = 0.0;
                    dist = 1.0;
                }
                let noise_x = (random_fn.call0()?.extract::<f64>()? - 0.5) * 0.05;
                let noise_y = (random_fn.call0()?.extract::<f64>()? - 0.5) * 0.05;

                let fx = (dx / dist) * nudge_step + noise_x;
                let fy = (dy / dist) * nudge_step + noise_y;

                let p1x = pos1.get_item(0)?.extract::<f64>()?;
                let p1y = pos1.get_item(1)?.extract::<f64>()?;
                let p2x = pos2.get_item(0)?.extract::<f64>()?;
                let p2y = pos2.get_item(1)?.extract::<f64>()?;

                let npos1 = PyTuple::new(py, [(p1x - fx).into_pyobject(py)?.into_any(), (p1y - fy).into_pyobject(py)?.into_any()])?;
                placements_dict.set_item(&ref1, npos1)?;
                let npos2 = PyTuple::new(py, [(p2x + fx).into_pyobject(py)?.into_any(), (p2y + fy).into_pyobject(py)?.into_any()])?;
                placements_dict.set_item(&ref2, npos2)?;

                let clamped1 = clamp_position.call1((placements_dict.get_item(&ref1)?,))?;
                placements_dict.set_item(&ref1, clamped1)?;
                let clamped2 = clamp_position.call1((placements_dict.get_item(&ref2)?,))?;
                placements_dict.set_item(&ref2, clamped2)?;
            }
        }

        let final_collisions = find_collisions.call1((&placements_dict,))?;
        if final_collisions.len()? > 0 {
            let msg = d6_util::py_format(
                py,
                "DEBUG: CourtyardCheck Failed to resolve {} pairs after {} iterations",
                &[
                    final_collisions.len()?.into_pyobject(py)?.into_any(),
                    max_iterations.into_pyobject(py)?.into_any(),
                ],
            )?;
            d6_util::py_print(py, &[msg])?;
            for pair in final_collisions.try_iter()? {
                let pair = pair?;
                let msg = d6_util::py_format(
                    py,
                    "DEBUG: Conflict: {} <-> {}",
                    &[pair.get_item(0)?.into_any(), pair.get_item(1)?.into_any()],
                )?;
                d6_util::py_print(py, &[msg])?;
            }
        }

        let frozenset_cls = builtins.getattr("frozenset")?;
        let new_placements = frozenset_cls.call1((placements_dict.call_method0("items")?,))?;
        let mut new_state = state;
        new_state.placements = Some(new_placements.into_any().unbind());
        Ok(new_state)
    }
}

#[cfg(feature = "python")]
/// FFI entry for the Python shim: `run_courtyard_check(state, stage)` (the
/// stage instance carries the courtyards / board dims / iteration config and
/// the `_find_collisions` / `_clamp_position` call-backs).
#[pyfunction]
pub fn run_courtyard_check(
    py: Python<'_>,
    state: Py<PyAny>,
    stage: Py<PyAny>,
) -> PyResult<Py<PyAny>> {
    let rust_state = crate::d1_bridge::from_python(py, state.bind(py)).map_err(|e| {
        pyo3::exceptions::PyRuntimeError::new_err(format!("{STAGE_NAME}: {e}"))
    })?;
    let rust_stage = CourtyardCheckStage { stage };
    let out = rust_stage
        .run(rust_state)
        .map_err(|e| crate::config_attach_stage::to_pyerr(&e))?;
    crate::d1_bridge::to_python(py, state.bind(py), &out, &["placements"])
}
