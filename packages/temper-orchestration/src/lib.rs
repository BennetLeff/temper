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
// - `derivation_stage` — U4: `DerivationStage` wraps the derivation
//                     feasibility kernels (`derive_*`) as a
//                     `Stage<BoardState>` implementor
// - `preflight_stage`  — U4: `PreflightStage` wraps the preflight
//                     feasibility kernels (`component_area_ratio`,
//                     `proximity_rule_impossible`, `zone_over_capacity`,
//                     `loop_area_violation`, `isolation_barrier_too_large`)
//                     as a `Stage<BoardState>` implementor
// - `explainability` — Phase-A U8: the explainability DATA CONTRACTS
//                     (`Decision`, `Alternative`, `DecisionTrace`, `Entry`,
//                     `Trace` pyclasses) and the `MarkdownReport` renderers
//                     (`render_markdown_report` / `render_component_report`),
//                     bit-exact with `explainability/{decision,trace,
//                     markdown_report}.py` (oracles in the temper-placer test
//                     tree); the NL-generation kernels stay single-source in
//                     temper-io-types and are called back from the pyclasses
// - `grid_stage`    — Phase D batch D3: the deterministic clearance-grid
//                     stage (`ClearanceGridStage` implements `Stage<BoardState>`,
//                     mirroring `deterministic/stages/_grid_stage.py`: pad
//                     collection, per-net blocking, HV creepage expansion,
//                     fence invocation, EXP-13 exclusion zones; the
//                     `ClearanceGrid` data type and the `_grid_hv`/`_grid_fence`
//                     helpers stay Python)
// - `grid_hv`       — Phase D batch D3: `run_hv_pad_set` (the
//                     `_grid_hv.hv_pad_set` orchestration: zone -> HV
//                     component resolution with the temper-geometry spatial
//                     fallback, `ConfigError` raising, pad-set assembly)
// - `grid_fence`    — Phase D batch D3: `run_grid_fence_check` + 
//                     `run_grid_perf_budget` (the `_grid_fence`
//                     conservatism-fence and perf-budget orchestration with
//                     CPython-`__format__`-rendered messages)
// - `component_assignment_stage` — Phase D batch D4: the
//                     `ComponentAssignmentStage` `Stage<BoardState>` impl
//                     (mirroring `deterministic/stages/component_assignment.py`:
//                     the state guards, `_domain_lookups`, the GEOS domain
//                     filter precomputed into the per-ref `domain_ok` set
//                     through the shapely objects at runtime, the
//                     sheetpath-first fixed-placement resolution, the
//                     design-bundle greedy kernel call and the
//                     `frozenset(placements.items())` write)
// - `phased_component_assignment_validator_stage` — Phase D batch D4:
//                     `run_phased_validator_hv` (the
//                     `phased_component_assignment_validator.py` coverage /
//                     non-over-claim DRC-fence scans, returning
//                     `(field, value, reason)` triples the Python shim wraps
//                     in the router_v6 `StageDRCFailure`; the slot-grid
//                     kernels stay single-source in design-bundle, the D5
//                     mixin helpers are called on a `__new__`-constructed
//                     stage exactly like the oracle)
//
// Panic safety at the boundary (R1g): pyo3's `#[pyfunction]` expansion
// wraps every exported body in `catch_unwind` and converts a Rust panic
// into `PyPanicException`, so no panic can unwind across the pyo3 frame
// into CPython (the crate also sets `profile.release.panic = "unwind"` so
// that catch is what runs).
mod board_state;
mod component_assignment_stage;
mod config_attach_stage;
mod convergence;
mod copper_length;
mod d1_bridge;
mod derivation_stage;
mod explainability;
mod feasibility;
mod grid_fence;
mod grid_hv;
mod grid_stage;
mod host_math;
mod net_ordering_stage;
mod phased_component_assignment_validator_stage;
mod pipeline;
mod pipeline_state;
mod preflight_stage;
mod setup_stage;
mod slot_generation_stage;
mod stage;
mod timing;
mod trace_filter;
mod zone_assignment_stage;
mod zone_geometry_stage;

// Public re-exports for the orchestration engine's Rust consumers (the
// runner test in `tests/stages_runner.rs` and the Phase-C pipeline wiring).
// Append-only per the U4 dispatch; the individual modules stay private.
pub use board_state::BoardState;
pub use component_assignment_stage::ComponentAssignmentStage;
pub use config_attach_stage::ConfigAttachStage;
pub use derivation_stage::DerivationStage;
pub use grid_stage::ClearanceGridStage;
pub use net_ordering_stage::NetOrderingStage;
pub use pipeline::{PipelineConfig, PipelineRunner, StageOutcome, StageReport};
pub use phased_component_assignment_validator_stage::phased_validator_hv;
pub use preflight_stage::PreflightStage;
pub use setup_stage::{DrcOracleSetupStage, NetClassSetupStage};
pub use slot_generation_stage::SlotGenerationStage;
pub use stage::{Stage, StageError, StageErrorKind};
pub use zone_assignment_stage::ZoneAssignmentStage;
pub use zone_geometry_stage::ZoneGeometryStage;

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
    m.add_class::<explainability::Alternative>()?;
    m.add_class::<explainability::Decision>()?;
    m.add_class::<explainability::DecisionTrace>()?;
    m.add_class::<explainability::Entry>()?;
    m.add_class::<explainability::Trace>()?;
    m.add_function(wrap_pyfunction!(explainability::render_markdown_report, m)?)?;
    m.add_function(wrap_pyfunction!(explainability::render_component_report, m)?)?;
    m.add_function(wrap_pyfunction!(config_attach_stage::run_config_attach, m)?)?;
    m.add_function(wrap_pyfunction!(net_ordering_stage::run_net_ordering, m)?)?;
    m.add_function(wrap_pyfunction!(setup_stage::run_drc_oracle_setup, m)?)?;
    m.add_function(wrap_pyfunction!(setup_stage::run_net_class_setup, m)?)?;
    m.add_function(wrap_pyfunction!(zone_geometry_stage::run_zone_geometry, m)?)?;
    m.add_function(wrap_pyfunction!(zone_assignment_stage::run_zone_assignment, m)?)?;
    m.add_function(wrap_pyfunction!(slot_generation_stage::run_slot_generation, m)?)?;
    m.add_function(wrap_pyfunction!(grid_stage::run_clearance_grid_stage, m)?)?;
    m.add_function(wrap_pyfunction!(grid_hv::run_hv_pad_set, m)?)?;
    m.add_function(wrap_pyfunction!(grid_fence::run_grid_fence_check, m)?)?;
    m.add_function(wrap_pyfunction!(grid_fence::run_grid_perf_budget, m)?)?;
    m.add_function(wrap_pyfunction!(component_assignment_stage::run_component_assignment, m)?)?;
    m.add_function(wrap_pyfunction!(component_assignment_stage::run_component_assignment_kernel, m)?)?;
    m.add_function(wrap_pyfunction!(phased_component_assignment_validator_stage::run_phased_validator_hv, m)?)?;
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
