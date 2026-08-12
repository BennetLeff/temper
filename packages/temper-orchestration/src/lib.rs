// WASM tier R1 (plan 2026-08-03-002): with `--no-default-features` the whole
// pyo3 surface (every `#[cfg(feature = "python")]`-gated item across this
// crate's stage modules) is not compiled, so the pure helpers/types those
// items call or reference look unused to rustc -- it cannot see past the cfg
// gate. Allow dead_code in that configuration only, exactly as
// `temper-io-types` and `temper-quality-oracle` do; the default (python)
// build keeps the lint.
#![cfg_attr(not(feature = "python"), allow(dead_code))]

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
// - `stage_ledger`  — router_v6/stage_ledger.py: snapshot_cardinality
//                     (the `_snapshot` counting), diff_cardinality (the
//                     `_diff` compare), CardinalitySnapshot (the
//                     `_CardinalitySnapshot` dataclass) — the final portable
//                     router_v6 orchestration module
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
mod apply_placements_stage;
pub(crate) mod channel_mapping;
pub(crate) mod clearance;
mod component_assignment_stage;
mod config_attach_stage;
mod connectivity_validation_stage;
mod convergence;
pub(crate) mod copper_length;
mod courtyard_check_stage;
mod d1_bridge;
mod d6_util;
mod derivation_stage;
// Orchestration-port unit U-E (Rust Orchestration Engine plan 2026-08-09-001):
// the `DeterministicPipeline` pyclass hosting the `create_drc_aware_pipeline()`
// stage factory (the D1->D7 ORDER) and the `DeterministicPipeline.run()`
// sequencing loop (driving the stages through `PipelineRunner<BoardState>`).
// Append-only per the U-E dispatch.
mod deterministic_pipeline;
mod drc_sweep_stage;
mod drc_validation_stage;
pub(crate) mod explainability;
pub(crate) mod feasibility;
mod fine_pitch_escape_stage;
mod grid_fence;
mod grid_hv;
pub(crate) mod grid_stage;
pub(crate) mod host_math;
mod hv_lv_partition_stage;
mod layer_assignment_stage;
mod net_ordering_stage;
pub(crate) mod phased_assignment_stage;
pub(crate) mod phased_component_assignment_validator_stage;
pub(crate) mod pipeline;
pub(crate) mod pipeline_state;
mod placement_validation_stage;
mod power_plane_stage;
mod preflight_stage;
// Orchestration-port unit U-G (Rust Orchestration Engine plan 2026-08-09-001):
// the `RouterPipeline` pyclass hosting the RouterV6Pipeline.run() stage-
// sequencing driver (the fixed Stage 0..5 order + the conditionals + the
// result assembly, driving the Python leaf call-backs through
// `PipelineRunner<BoardState>`). Append-only per the U-G dispatch.
pub(crate) mod router_pipeline;
mod setup_stage;
mod slot_generation_stage;
pub(crate) mod stage;
pub(crate) mod stage_ledger;
pub(crate) mod timing;
mod trace_filter;
mod via_validation_stage;
mod zone_assignment_stage;
mod zone_geometry_stage;
pub(crate) mod zone_aware_slot_generation_stage;

// Deterministic SplitMix64 generator shared by the `proptest`-mirroring
// campaigns added to `timing`/`host_math`/`copper_length`/`clearance`/
// `grid_stage`/`phased_assignment_stage`/`zone_aware_slot_generation_stage`/
// `phased_component_assignment_validator_stage`'s own `tests` submodules (R19
// U6: mirror the 45 proptest-dev-dependency properties onto the wasm32 tier
// -- see `wasm_campaign_prng.rs`'s own header). Declared UNCONDITIONALLY here
// -- the file's own top-level `#![cfg(any(test, feature = "wasm-registry"))]`
// attribute gates its content instead (it has no purpose in a plain `cargo
// build --features python` release binary, but is needed under plain `cargo
// test` too, since the mirror tests run natively as well as on wasm32 -- both
// run, per this campaign's whole point). Gating THIS declaration line with
// the identical `#[cfg(any(test, feature = "wasm-registry"))]` string instead
// would make `scripts/gen_wasm_test_registry.py`'s census misread the
// declaration itself as a second, contentless test module up for
// registration (it pattern-matches that exact string as a test gate) --
// harmless (an accepted `no-test-functions` exclusion, `--check` still
// passes) but confusing noise in `--census` output, so the gate lives on the
// file instead.
pub(crate) mod wasm_campaign_prng;

// NOT gated on `python`. The wasm32 tier builds with --no-default-features,
// so an added `python` gate here would silently exclude the registry and the
// runner would fail to compile against it. `wasm-registry` is implied by every
// per-family feature and by `wasm-test-registry`, so any wasm build compiles
// this module.
// Generated by `scripts/gen_wasm_test_registry.py --crate temper-orchestration`.
#[cfg(feature = "wasm-registry")]
pub mod wasm_test_registry;

// Phase E batch E6 (Rust Orchestration Engine plan 2026-08-09-001): the
// pipeline-route orchestration — the router_v6/_pipeline_route.py and
// router_v6/_adapter_convert.py shims delegate to the `run_*` pyfunctions
// here; the Stage impl is the E6 runner surface (see `pipeline_route.rs`'s
// header for the migrated/kept-Python split and the E6 boundary). Append-only
// per the U4 dispatch.
pub(crate) mod pipeline_route;

// Wave-4 tail-tooling: the regression reporter surface
// (temper_placer/regression/reporter.py) — `MetricDelta` /
// `BoardResult` / `BatteryVerdictReport` / `RegressionReporter` pyclasses
// carrying the metric-delta computation and verdict/result formatting. The
// Python module is now a delegation shim re-exporting these classes;
// bit-identical parity is pinned by
// `tests/regression/test_reporter_rust_differential.py`. Append-only per
// the tail-tooling dispatch.
pub(crate) mod reporter;

// Phase C residual (Rust Orchestration Engine plan 2026-08-09-001, U4-style
// dispatch): the pipeline-contract tail — `pipeline/dag_types.py` →
// `dag_types` (the `StageResult` dataclass), `pipeline/dag_observability.py`
// → `dag` (the `StageEvent` / `PipelineExecutionLog` observability
// dataclasses + the asdict `to_dict` serialization), `pipeline/
// bottleneck_report.py` → `bottleneck` (`BottleneckNetEntry` /
// `BottleneckRegion` / `CongestionHeatmapData` / `BottleneckReport` /
// `DeclaredArtifact`), `pipeline/metrics_observer.py` → `metrics`
// (`MetricsObserver` + `CanaryCheckError` + `CrossValidationError`). Each
// Python module is a thin delegation shim re-exporting these pyclasses;
// bit-identical parity is pinned by
// `tests/pipeline/test_phase_c_tail_rust_differential.py` against the
// verbatim pre-migration oracles. `dag_expr.py`'s parser already lives in
// temper-io-types (out of scope here); the DAG exception classes the shim
// needs stay Python. Append-only per the U4 dispatch.
pub(crate) mod bottleneck;
pub(crate) mod dag;
pub(crate) mod dag_types;
pub(crate) mod metrics;

// Public re-exports for the orchestration engine's Rust consumers (the
// runner test in `tests/stages_runner.rs` and the Phase-C pipeline wiring).
// Append-only per the U4 dispatch; the individual modules stay private.
pub use apply_placements_stage::ApplyPlacementsStage;
#[cfg(feature = "python")]
pub use board_state::BoardState;
#[cfg(feature = "python")]
pub use channel_mapping::{ChannelMappingStage, ChannelWidthsStage};
#[cfg(feature = "python")]
pub use clearance::{
    ClearanceCheckStage, ClearanceEngineStage, CreepageCheckStage, DomainClearanceStage,
    IsolationBarrierStage,
};
#[cfg(feature = "python")]
pub use component_assignment_stage::ComponentAssignmentStage;
#[cfg(feature = "python")]
pub use config_attach_stage::ConfigAttachStage;
pub use connectivity_validation_stage::ConnectivityValidationStage;
#[cfg(feature = "python")]
pub use courtyard_check_stage::CourtyardCheckStage;
pub use derivation_stage::DerivationStage;
#[cfg(feature = "python")]
pub use deterministic_pipeline::{DeterministicPipeline, drc_aware_stage_order};
pub use drc_sweep_stage::{DRCSweepStage, ShortCircuitDetectionStage, TrackDeduplicationStage};
pub use drc_validation_stage::DRCValidationStage;
#[cfg(feature = "python")]
pub use fine_pitch_escape_stage::FinePitchEscapeStage;
#[cfg(feature = "python")]
pub use grid_stage::ClearanceGridStage;
pub use hv_lv_partition_stage::HvLvPartitionStage;
#[cfg(feature = "python")]
pub use layer_assignment_stage::LayerAssignmentStage;
#[cfg(feature = "python")]
pub use net_ordering_stage::NetOrderingStage;
#[cfg(feature = "python")]
pub use phased_assignment_stage::PhasedAssignmentStage;
pub use pipeline::{PipelineConfig, PipelineRunner, StageOutcome, StageReport};
#[cfg(feature = "python")]
pub use phased_component_assignment_validator_stage::phased_validator_hv;
#[cfg(feature = "python")]
pub use placement_validation_stage::PlacementValidationStage;
#[cfg(feature = "python")]
pub use pipeline_route::PipelineRouteStage;
#[cfg(feature = "python")]
pub use power_plane_stage::PowerPlaneStage;
pub use preflight_stage::PreflightStage;
#[cfg(feature = "python")]
pub use router_pipeline::RouterPipeline;
#[cfg(feature = "python")]
pub use setup_stage::{DrcOracleSetupStage, NetClassSetupStage};
pub use slot_generation_stage::SlotGenerationStage;
#[cfg(feature = "python")]
pub use stage::{Stage, StageError, StageErrorKind};
pub use via_validation_stage::{ViaDeduplicationStage, ViaValidationStage};
pub use zone_assignment_stage::ZoneAssignmentStage;
#[cfg(feature = "python")]
pub use zone_geometry_stage::ZoneGeometryStage;
#[cfg(feature = "python")]
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
    m.add_function(wrap_pyfunction!(fine_pitch_escape_stage::run_fine_pitch_escape, m)?)?;
    m.add_function(wrap_pyfunction!(hv_lv_partition_stage::run_hv_lv_partition, m)?)?;
    m.add_function(wrap_pyfunction!(power_plane_stage::run_power_plane, m)?)?;
    m.add_function(wrap_pyfunction!(layer_assignment_stage::run_layer_assignment, m)?)?;
    m.add_function(wrap_pyfunction!(apply_placements_stage::run_apply_placements, m)?)?;
    m.add_function(wrap_pyfunction!(clearance::get_clearance_py, m)?)?;
    m.add_function(wrap_pyfunction!(clearance::run_clearance_check, m)?)?;
    m.add_function(wrap_pyfunction!(clearance::run_creepage_check, m)?)?;
    m.add_function(wrap_pyfunction!(clearance::classify_domain_partition_py, m)?)?;
    m.add_function(wrap_pyfunction!(clearance::project_onto_barrier_axis_py, m)?)?;
    m.add_function(wrap_pyfunction!(clearance::evaluate_isolator_feasibility_py, m)?)?;
    m.add_function(wrap_pyfunction!(clearance::domain_clearance_constraints_py, m)?)?;
    m.add_function(wrap_pyfunction!(clearance::keepaway_constraints_py, m)?)?;
    m.add_function(wrap_pyfunction!(clearance::intra_footprint_conflicts_py, m)?)?;
    m.add_function(wrap_pyfunction!(clearance::audit_domain_clearance_py, m)?)?;
    m.add_function(wrap_pyfunction!(channel_mapping::run_channel_mapping, m)?)?;
    m.add_function(wrap_pyfunction!(channel_mapping::run_fallback_channel_path, m)?)?;
    m.add_function(wrap_pyfunction!(channel_mapping::run_validated_two_pad_terminals, m)?)?;
    m.add_function(wrap_pyfunction!(channel_mapping::run_expand_all_pad_tree, m)?)?;
    m.add_function(wrap_pyfunction!(channel_mapping::run_assign_layer, m)?)?;
    m.add_function(wrap_pyfunction!(channel_mapping::run_channel_widths_edt, m)?)?;
    m.add_function(wrap_pyfunction!(pipeline_route::run_select_sat_nets, m)?)?;
    m.add_function(wrap_pyfunction!(pipeline_route::run_build_clause_origin, m)?)?;
    m.add_function(wrap_pyfunction!(pipeline_route::run_select_routing_grids, m)?)?;
    m.add_function(wrap_pyfunction!(pipeline_route::run_next_tstamp, m)?)?;
    m.add_function(wrap_pyfunction!(pipeline_route::run_to_stage0_netclass_rules, m)?)?;
    m.add_function(wrap_pyfunction!(pipeline_route::run_write_route_segments, m)?)?;
    // Phase C residual (append-only per the U4 dispatch): the pipeline
    // contract tail — dag_types / dag / bottleneck / metrics.
    m.add_class::<dag_types::StageResult>()?;
    m.add_class::<dag::StageEvent>()?;
    m.add_class::<dag::PipelineExecutionLog>()?;
    m.add_class::<bottleneck::BottleneckNetEntry>()?;
    m.add_class::<bottleneck::BottleneckRegion>()?;
    m.add_class::<bottleneck::CongestionHeatmapData>()?;
    m.add_class::<bottleneck::BottleneckReport>()?;
    m.add_class::<bottleneck::DeclaredArtifact>()?;
    m.add_class::<metrics::MetricsObserver>()?;
    m.add("CrossValidationError", m.py().get_type::<metrics::CrossValidationError>())?;
    m.add("CanaryCheckError", m.py().get_type::<metrics::CanaryCheckError>())?;
    // The final router_v6 orchestration slice (Rust Orchestration Engine plan
    // 2026-08-09-001): the stage_ledger cardinality compute —
    // `snapshot_cardinality` (`_snapshot`), `diff_cardinality` (`_diff`) and
    // the `CardinalitySnapshot` pyclass (`_CardinalitySnapshot`). The shim
    // wires all three; the stateful `StageLedger` orchestration and the
    // presentation stay Python. Append-only per the U4 dispatch.
    m.add_class::<stage_ledger::CardinalitySnapshot>()?;
    m.add_function(wrap_pyfunction!(stage_ledger::snapshot_cardinality, m)?)?;
    m.add_function(wrap_pyfunction!(stage_ledger::diff_cardinality, m)?)?;
    // Wave-4 tail-tooling: the regression reporter surface
    // (regression/reporter.py) — all four pyclasses re-exported by the
    // delegating shim (public API unchanged).
    m.add_class::<reporter::BatteryVerdictReport>()?;
    m.add_class::<reporter::MetricDelta>()?;
    m.add_class::<reporter::BoardResult>()?;
    m.add_class::<reporter::RegressionReporter>()?;
    // Orchestration-port unit U-E (append-only per the U-E dispatch): the
    // DeterministicPipeline pyclass -- the create_drc_aware_pipeline()
    // stage factory (the D1->D7 ORDER) and the DeterministicPipeline.run()
    // sequencing loop (through PipelineRunner<BoardState>). The
    // deterministic/__init__.py shim delegates run() + the factory here.
    m.add_class::<deterministic_pipeline::DeterministicPipeline>()?;
    // Orchestration-port unit U-G (append-only per the U-G dispatch): the
    // RouterPipeline pyclass -- the RouterV6Pipeline.run() stage-sequencing
    // driver. The router_v6/_pipeline_core.py shim delegates run() here.
    m.add_class::<router_pipeline::RouterPipeline>()?;
    Ok(())
}

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    #[cfg_attr(test, test)]
    fn module_exports_exist() {
        // Compile-time sanity: the five exported names exist on their
        // modules. The behavioural proof is the differential suite.
        let _ = super::timing::compare_stage(0.0, 1.0, 0.2, 10.0);
        let _ = super::copper_length::measure_copper_length(vec![]);
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("tests::module_exports_exist", module_exports_exist),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}
