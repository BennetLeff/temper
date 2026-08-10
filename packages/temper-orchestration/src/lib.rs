// temper-orchestration: the orchestration compute of the Wave-4 Phase-5
// Python→Rust migration slice (cli/adapters/temper-workflow).
//
// Surfaces hosted here (each with its own module and a differential against
// a VERBATIM pre-migration oracle in the temper-placer / temper-workflow
// test trees; see this crate's VERIFICATION.md):
//
// - `timing`        — cli/timing.py: compare_stage, p95
// - `trace_filter`  — cli/trace_commands.py: filter_decisions,
//                     find_rejected_alternative
// - `copper_length` — temper-workflow routing/route_and_measure.py:
//                     measure_copper_length
// - `feasibility`   — pipeline/convergence.py + pipeline/preflight.py +
//                     pipeline/derivation.py: record_loss, check_success,
//                     is_converged, check_routability_regression,
//                     component_area_ratio, proximity_rule_impossible,
//                     zone_over_capacity, loop_area_violation,
//                     isolation_barrier_too_large, derive_* and the
//                     min-clearance extraction (pipeline-feasibility slice)
//
// The Rust orchestration engine (Rust Orchestration Engine plan
// 2026-08-09-001, U0 scaffolding + U1 convergence) lives here too:
//
// - `stage`        — the `Stage<S>` trait, `StageError`, `InvariantSpec`,
//                     `DeclaredArtifact` (the migration interface)
// - `pipeline`     — `PipelineRunner<S>`, `PipelineReport`/`StageReport`,
//                     `PipelineObserver<S>`, `PipelineConfig`
// - `board_state`  — the phased `BoardState` struct (D2: mostly
//                     `Option<Py<PyAny>>` until Phase A marshalling types land)
// - `convergence`  — the Phase-1 deliverable: `TerminationReason`,
//                     `ConvergenceCriteria`, `ConvergenceState`,
//                     `ConvergenceChecker` pyclasses bit-exact with
//                     `pipeline/convergence.py`; `ConvergenceChecker` also
//                     implements `Stage<BoardState>` (stub)
// - `pipeline_state` — the U4 deliverable: `PipelinePhase`, `PipelineConfig`,
//                     `PipelineState` pyclasses bit-exact with
//                     `pipeline/state.py` (PipelineError stays Python);
//                     `PipelineConfig` is the U4 "PipelineState→Rust config"
//                     migration of the plan's Phase C row
//
// Panic safety at the boundary (R1g): pyo3's `#[pyfunction]` expansion
// wraps every exported body in `catch_unwind` and converts a Rust panic
// into `PyPanicException`, so no panic can unwind across the pyo3 frame
// into CPython (the crate also sets `profile.release.panic = "unwind"` so
// that catch is what runs).
mod board_state;
mod convergence;
mod copper_length;
mod feasibility;
mod host_math;
mod pipeline;
mod pipeline_state;
mod stage;
mod timing;
mod trace_filter;

#[cfg(feature = "python")]
use pyo3::prelude::*;

#[cfg(feature = "python")]
#[pymodule]
fn temper_orchestration(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(timing::compare_stage, m)?)?;
    m.add_function(wrap_pyfunction!(timing::p95, m)?)?;
    m.add_function(wrap_pyfunction!(trace_filter::filter_decisions, m)?)?;
    m.add_function(wrap_pyfunction!(trace_filter::find_rejected_alternative, m)?)?;
    m.add_function(wrap_pyfunction!(copper_length::measure_copper_length, m)?)?;
    m.add_function(wrap_pyfunction!(feasibility::record_loss, m)?)?;
    m.add_function(wrap_pyfunction!(feasibility::check_success, m)?)?;
    m.add_function(wrap_pyfunction!(feasibility::is_converged, m)?)?;
    m.add_function(wrap_pyfunction!(feasibility::check_routability_regression, m)?)?;
    m.add_function(wrap_pyfunction!(feasibility::component_area_ratio, m)?)?;
    m.add_function(wrap_pyfunction!(feasibility::proximity_rule_impossible, m)?)?;
    m.add_function(wrap_pyfunction!(feasibility::zone_over_capacity, m)?)?;
    m.add_function(wrap_pyfunction!(feasibility::loop_area_violation, m)?)?;
    m.add_function(wrap_pyfunction!(feasibility::isolation_barrier_too_large, m)?)?;
    m.add_function(wrap_pyfunction!(feasibility::derive_emi_max_dist, m)?)?;
    m.add_function(wrap_pyfunction!(feasibility::derive_thermal_clearance, m)?)?;
    m.add_function(wrap_pyfunction!(feasibility::derive_si_max_placement_dist, m)?)?;
    m.add_function(wrap_pyfunction!(feasibility::mains_voltage_to_class_code, m)?)?;
    m.add_function(wrap_pyfunction!(feasibility::extract_min_clearance, m)?)?;
    m.add_class::<convergence::ConvergenceChecker>()?;
    m.add_class::<convergence::ConvergenceCriteria>()?;
    m.add_class::<convergence::ConvergenceState>()?;
    m.add_class::<convergence::TerminationReason>()?;
    m.add_class::<pipeline_state::PipelinePhase>()?;
    m.add_class::<pipeline_state::PipelineConfig>()?;
    m.add_class::<pipeline_state::PipelineState>()?;
    Ok(())
}

#[cfg(test)]
mod tests {
    #[test]
    fn module_exports_exist() {
        // Compile-time sanity: the five exported names exist on their
        // modules. The behavioural proof is the differential suite.
        let _ = super::timing::compare_stage(0.0, 1.0, 0.2, 10.0);
        let _ = super::copper_length::measure_copper_length(vec![]);
    }
}
