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
// - `zone_aware_slot_generation_stage` — Phase D batch D5: the
//                     `ZoneAwareSlotGenerationStage` `Stage<BoardState>` impl
//                     (mirroring `deterministic/stages/zone_aware_slot_generation.py`:
//                     the `_isolation_filter` + K4 reclaim, `_get_copper_zones`,
//                     the per-zone copper + isolation-cutout slot walk and the
//                     `zone_slots` / `reclaim_by_pin_pair` writes; the
//                     slot-grid / ray-casting / AABB leaf kernels, the
//                     `POWER_NET_NAMES` classification set and the
//                     `isolation_slot_aabb` stay single-source in
//                     design-bundle / Python and are driven through FFI)
// - `placement_validation_stage` — Phase D batch D6: the
//                     `PlacementValidationStage` `Stage<BoardState>` impl
//                     (mirroring `deterministic/stages/placement_validation.py`:
//                     the no-board guard, the component-position extraction,
//                     the proximity / signal-HV sweeps calling the Python
//                     `_validate_proximity` / `_validate_signal_hv` helpers
//                     back, the hard-violation filter + raise message and the
//                     `placement_violations` write)
// - `via_validation_stage` — Phase D batch D6: the `ViaValidationStage` +
//                     `ViaDeduplicationStage` `Stage<BoardState>` impls
//                     (mirroring `deterministic/stages/via_validation.py`: the
//                     guards, the trace-endpoint / pin-position index building,
//                     the per-via validity sweep, the `print` messages and the
//                     `vias` frozenset writes; the temper-drc-rs
//                     count_connected_layers / dedup kernels stay single-source)
// - `drc_sweep_stage` — Phase D batch D6: the `DRCSweepStage` +
//                     `TrackDeduplicationStage` + `ShortCircuitDetectionStage`
//                     `Stage<BoardState>` impls (mirroring
//                     `deterministic/stages/drc_sweep.py`: the guards, the
//                     oracle call-backs, the non-Trace pass-through, the
//                     pin_net_map build with CPython `round(x, 2)` keys and
//                     the routes/vias frozenset writes)
// - `drc_validation_stage` — Phase D batch D6: the `DRCValidationStage`
//                     `Stage<BoardState>` impl (mirroring
//                     `deterministic/stages/drc_validation.py`: the
//                     `validate_all` call-back, the count-by-type summary, the
//                     `threshold_decision_py` raise decision and the
//                     `drc_violations` write)
// - `connectivity_validation_stage` — Phase D batch D6: the
//                     `ConnectivityValidationStage` `Stage<BoardState>` impl
//                     (mirroring `deterministic/stages/connectivity_validation.py`:
//                     the geometry extraction + per-net grouping, the
//                     plane-net / empty-net skips, the UnionFind kernel
//                     marshalling and the `connectivity_violations` write)
// - `courtyard_check_stage` — Phase D batch D6: the `CourtyardCheckStage`
//                     `Stage<BoardState>` impl (mirroring
//                     `deterministic/stages/courtyard_check.py`: the iterative
//                     nudge loop with the libm-`pow` distance, the
//                     `_find_collisions` / `_clamp_position` call-backs and
//                     the `placements` write; the shapely/GEOS collision
//                     detection and the CPython `random.random()` noise stay
//                     single-source)
//
// The D6 stages share the `(state, message)` raise channel
// (`d6_util::write_back_or_raise`): a run() that decides to raise returns
// `Err(StageErrorKind::Infeasible)` and the pyfunction hands the message to
// the shim, which raises its module's own exception type (the exception
// classes stay Python; the decision + message are the migrated orchestration).
// The shared helpers (`py_print` / `py_format` / `log_msg`) in `d6_util.rs`
// route every rendered message through CPython (`print` / `str.format` /
// `logging`), so David-Gay decimal formatting and tuple reprs stay
// bit-identical to the pre-migration Python by construction.
//
// Panic safety at the boundary (R1g): pyo3's `#[pyfunction]` expansion
// wraps every exported body in `catch_unwind` and converts a Rust panic
// into `PyPanicException`, so no panic can unwind across the pyo3 frame
// into CPython (the crate also sets `profile.release.panic = "unwind"` so
// that catch is what runs).
mod board_state;
mod component_assignment_stage;
mod config_attach_stage;
mod connectivity_validation_stage;
mod convergence;
mod copper_length;
mod courtyard_check_stage;
mod d1_bridge;
mod d6_util;
mod derivation_stage;
mod drc_sweep_stage;
mod drc_validation_stage;
mod explainability;
mod feasibility;
mod grid_fence;
mod grid_hv;
mod grid_stage;
mod host_math;
mod net_ordering_stage;
mod phased_assignment_stage;
mod phased_component_assignment_validator_stage;
mod pipeline;
mod pipeline_state;
mod placement_validation_stage;
mod preflight_stage;
mod setup_stage;
mod slot_generation_stage;
mod stage;
mod timing;
mod trace_filter;
mod via_validation_stage;
mod zone_assignment_stage;
mod zone_geometry_stage;
mod zone_aware_slot_generation_stage;

// Public re-exports for the orchestration engine's Rust consumers (the
// runner test in `tests/stages_runner.rs` and the Phase-C pipeline wiring).
// Append-only per the U4 dispatch; the individual modules stay private.
pub use board_state::BoardState;
pub use component_assignment_stage::ComponentAssignmentStage;
pub use config_attach_stage::ConfigAttachStage;
pub use connectivity_validation_stage::ConnectivityValidationStage;
pub use courtyard_check_stage::CourtyardCheckStage;
pub use derivation_stage::DerivationStage;
pub use drc_sweep_stage::{DRCSweepStage, ShortCircuitDetectionStage, TrackDeduplicationStage};
pub use drc_validation_stage::DRCValidationStage;
pub use grid_stage::ClearanceGridStage;
pub use net_ordering_stage::NetOrderingStage;
pub use phased_assignment_stage::PhasedAssignmentStage;
pub use pipeline::{PipelineConfig, PipelineRunner, StageOutcome, StageReport};
pub use phased_component_assignment_validator_stage::phased_validator_hv;
pub use placement_validation_stage::PlacementValidationStage;
pub use preflight_stage::PreflightStage;
pub use setup_stage::{DrcOracleSetupStage, NetClassSetupStage};
pub use slot_generation_stage::SlotGenerationStage;
pub use stage::{Stage, StageError, StageErrorKind};
pub use via_validation_stage::{ViaDeduplicationStage, ViaValidationStage};
pub use zone_assignment_stage::ZoneAssignmentStage;
pub use zone_geometry_stage::ZoneGeometryStage;
pub use zone_aware_slot_generation_stage::ZoneAwareSlotGenerationStage;

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
    m.add_function(wrap_pyfunction!(zone_aware_slot_generation_stage::run_zone_aware_slot_generation, m)?)?;
    m.add_function(wrap_pyfunction!(phased_assignment_stage::run_phased_assignment, m)?)?;
    m.add_function(wrap_pyfunction!(phased_assignment_stage::run_phase_select_best_slot, m)?)?;
    m.add_function(wrap_pyfunction!(drc_validation_stage::run_drc_validation, m)?)?;
    m.add_function(wrap_pyfunction!(connectivity_validation_stage::run_connectivity_validation, m)?)?;
    m.add_function(wrap_pyfunction!(via_validation_stage::run_via_validation, m)?)?;
    m.add_function(wrap_pyfunction!(via_validation_stage::run_via_deduplication, m)?)?;
    m.add_function(wrap_pyfunction!(drc_sweep_stage::run_drc_sweep, m)?)?;
    m.add_function(wrap_pyfunction!(drc_sweep_stage::run_track_deduplication, m)?)?;
    m.add_function(wrap_pyfunction!(drc_sweep_stage::run_short_circuit_detection, m)?)?;
    m.add_function(wrap_pyfunction!(placement_validation_stage::run_placement_validation, m)?)?;
    m.add_function(wrap_pyfunction!(courtyard_check_stage::run_courtyard_check, m)?)?;
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
