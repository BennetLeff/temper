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
// - `feasibility`   — pipeline/convergence.py + pipeline/preflight.py +
//                     pipeline/derivation.py: record_loss, check_success,
//                     is_converged, check_routability_regression,
//                     component_area_ratio, proximity_rule_impossible,
//                     zone_over_capacity, loop_area_violation,
//                     isolation_barrier_too_large, derive_* and the
//                     min-clearance extraction (pipeline-feasibility slice)
// - `partition_planner` — deterministic coarse placement clusters.  Complete
//                     sorted pin-class signatures constrain electrical-net
//                     unions, so shared global rails cannot bridge safety
//                     domains; the plain tuple/list plan is the CP-SAT seam,
//                     with compact aspect-aware shelf envelope sizing and
//                     Rust-owned per-partition creepage gap reduction.
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
// - `marshal`      — the Phase-A boundary marshaller (unit O-C3/U0): the
//                     `Marshal` trait + `to_owned`/`to_python`, the `Val`
//                     int-or-float canonical type, the lossless `Plain` value
//                     tree, and the reusable round-trip gate. This is the
//                     foundation the U1+ units use to replace the 23
//                     `Option<Py<PyAny>>` BoardState fields with owned structs.
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
//                     `Trace` pyclasses; the former MarkdownReport binding
//                     was differential-only and is no longer exported,
//                     bit-exact with `explainability/{decision,trace}.py`
//                     (oracles in the temper-placer test
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
//                     slot-grid / ray-casting / AABB leaf kernels and the
//                     `POWER_NET_NAMES` classification set stay single-source
//                     in design-bundle / Python and are driven through FFI;
//                     isolation-slot AABB arithmetic is private to this stage)
// - `placement_validation_stage` — Phase D batch D6: the
//                     `PlacementValidationStage` `Stage<BoardState>` impl
//                     (mirroring `deterministic/stages/placement_validation.py`:
//                     the no-board guard, the component-position extraction,
//                     the proximity / signal-HV sweeps calling the
//                     temper-drc-rs kernels directly, the hard-violation
//                     filter + raise message and the
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
// - `deterministic_pipeline` — Phase U-E: the `DeterministicPipeline`
//                     pyclass hosting the `create_drc_aware_pipeline()`
//                     stage factory (the D1->D7 ORDER) and the
//                     `DeterministicPipeline.run()` sequencing loop
//                     (driving the Python shim stages through
//                     `PipelineRunner<BoardState>` with the fence
//                     invocation preserved; the Python `BoardState` threads
//                     through a shared side-channel)
// - `feedback_loop`  — Phase U-F: the `AutomatedZeroDRC` feedback loop of
//                     `deterministic/feedback/orchestrator.py` — the
//                     iterate-until-clean LOOP (solve -> DRC -> map ->
//                     adjust -> re-solve) as per-iteration shims through
//                     `PipelineRunner<BoardState>` (the U-E pattern); the
//                     per-iteration call-backs stay Python
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
mod apply_placements_stage;
mod board_state;
// Option-E subprocess serialization (2026-08-21): `NativeBoardState` <->
// JSON for the Rust CLI driver's per-stage Python subprocesses. Ungated
// (pure serde, no pyo3) so the wasm tier and the CLI both compile it.
pub mod state_ser;
// Option-E subprocess stage: `Stage<NativeBoardState>` over one
// `_stage_subprocess.py` invocation. Ungated like `state_ser`.
pub(crate) mod channel_mapping;
pub(crate) mod clearance;
mod component_assignment_stage;
pub mod subprocess_stage;
// 2026-08-17 placer constraint/clearance Rust-port stage 2: the
// `netclass_constraints.py` cross-class SEPARATED constraint orchestration
// (O(n^2) pairing loop, severity-rank component classification,
// class-pair-override lookup). See netclass.rs's own header comment.
pub(crate) mod netclass;
// Deterministic coarse placement partition contract.  The planner is pure
// Rust; only its plain tuple/list boundary is exposed through pyo3.
mod config_attach_stage;
mod connectivity_validation_stage;
mod convergence;
mod courtyard_check_stage;
mod d1_bridge;
mod d6_util;
mod derivation_stage;
pub(crate) mod partition_planner;
pub(crate) mod creepage_lower_bounds;
// Orchestration-port unit U-E (Rust Orchestration Engine plan 2026-08-09-001):
// the `DeterministicPipeline` pyclass hosting the `create_drc_aware_pipeline()`
// stage factory (the D1->D7 ORDER) and the `DeterministicPipeline.run()`
// sequencing loop (driving the stages through `PipelineRunner<BoardState>`).
// Append-only per the U-E dispatch.
mod deterministic_pipeline;
// Orchestration-port unit U-F (Rust Orchestration Engine plan 2026-08-09-001):
// the `AutomatedZeroDRC` feedback loop of
// `temper_placer/deterministic/feedback/orchestrator.py` -- the
// iterate-until-clean LOOP (solve -> DRC -> map -> adjust -> re-solve),
// wired through `PipelineRunner<BoardState>` as per-iteration shims (the
// U-E pattern). The `run_automated_zero_drc` pyfunction is the delegation
// target of the shim's `AutomatedZeroDRC.run()`; the per-iteration
// `FeedbackIterationStage` implements `Stage<BoardState>` so the runner's
// skip semantics ARE the loop's break semantics. Append-only per the U-F
// dispatch.
mod feedback_loop;
// Orchestration-port unit U-I (Rust Orchestration Engine plan 2026-08-09-001,
// Wave-4 CP-SAT placement-loop slice): the residual non-ortools orchestration
// of `temper_placer/placer/cp_sat/_loop_core.py` -- the loop SEQUENCING
// (legacy classifier loop + gate-driven loop), the gate checks, and the
// convergence/stability/feedback DECISIONS. The CP-SAT solve, routing,
// classifier, and the gate/field leaf helpers stay Python call-backs. The
// `cpsat_run_legacy_loop` / `cpsat_run_gated_loop` / `cpsat_solve_with_delta`
// / `cpsat_solve_phase2` pyfunctions are the delegation targets of the
// `_loop_core.py` mixin. Append-only per the U-I dispatch.
mod cpsat_loop;
// Orchestration-port unit U-I (Rust Orchestration Engine plan 2026-08-09-001,
// Wave-4 CP-SAT placement-loop slice): the `FeedbackClassifier.classify()`
// feedback-DECISION sequencing of `temper_placer/placer/cp_sat/feedback.py`.
// The `classify_feedback` pyfunction is the delegation target of the shim's
// `classify()`; congestion handling is Rust-owned while clearance and the
// remaining constraint-building handlers retain Python-object seams.
// Append-only per the U-I dispatch.
mod feedback;
// Orchestration-port unit U-I (Rust Orchestration Engine plan 2026-08-09-001,
// Wave-4 CP-SAT placement-loop slice): the RESIDUAL non-ortools orchestration
// of `temper_placer/placer/cp_sat/validator_audit.py` -- the R24 post-solve
// `audit_domain_clearance_validator()` audit SEQUENCING (the two ValueError
// guards, the validator-placement build, the REQ-SAFE-01 re-run, the
// geometry-trust computation + degraded-geometry logger.error, the
// covered-pairs build, the per-violation bucket dispatch + reason strings,
// and the result assembly). The `audit_domain_clearance_validator` pyfunction
// is the delegation target of the shim's function of the same name;
// `build_validator_placement` / the pad-schema serialization and
// `verify_iec60335_compliance` stay Python call-backs. Append-only per the
// U-I dispatch.
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
#[cfg(feature = "python")]
pub(crate) mod marshal;
mod validator_audit;
// Unit O-C3/U2: the owned leaf-struct boundary — `Marshal` impls for the
// `temper-data-model` `Component`/`Pin`/`Net` structs (python-gated: they
// are the pyo3 half of the data-model port; the structs themselves are pure
// Rust in the sibling crate).
mod net_ordering_stage;
#[cfg(feature = "python")]
pub(crate) mod netlist_owned;
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
pub(crate) mod zone_aware_slot_generation_stage;
mod zone_geometry_stage;

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
// dispatch): the pipeline-contract tail — `pipeline/dag_observability.py`
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
pub(crate) mod metrics;

// Public re-exports for the orchestration engine's Rust consumers (the
// runner test in `tests/stages_runner.rs` and the Phase-C pipeline wiring).
// Append-only per the U4 dispatch; the individual modules stay private.
pub use apply_placements_stage::ApplyPlacementsStage;
#[cfg(feature = "python")]
pub use board_state::{BoardState, RouteEntry, ViaEntry};
pub use board_state::{NativeBoardState, SlotId};
#[cfg(feature = "python")]
pub use channel_mapping::{ChannelMappingStage, ChannelWidthsStage};
#[cfg(feature = "python")]
pub use clearance::{ClearanceCheckStage, ClearanceEngineStage, CreepageCheckStage};
#[cfg(feature = "python")]
pub use component_assignment_stage::ComponentAssignmentStage;
#[cfg(feature = "python")]
pub use config_attach_stage::ConfigAttachStage;
pub use connectivity_validation_stage::ConnectivityValidationStage;
#[cfg(feature = "python")]
pub use courtyard_check_stage::CourtyardCheckStage;
pub use derivation_stage::DerivationStage;
// The D1->D7 stage ORDER (23 stages) is pure Rust (a const table + a pure
// substitution function over it) — ungated so the Rust CLI driver can drive
// the sequencing order without an interpreter. The `DeterministicPipeline`
// pyclass (the Python-driven run loop) stays python-gated.
#[cfg(feature = "python")]
pub use cpsat_loop::{
    cpsat_run_gated_loop, cpsat_run_legacy_loop, cpsat_solve_phase2, cpsat_solve_with_delta,
};
#[cfg(feature = "python")]
pub use deterministic_pipeline::DeterministicPipeline;
pub use deterministic_pipeline::drc_aware_stage_order;
pub use drc_sweep_stage::{DRCSweepStage, ShortCircuitDetectionStage, TrackDeduplicationStage};
pub use drc_validation_stage::DRCValidationStage;
#[cfg(feature = "python")]
pub use feedback::{
    classify_feedback, compute_heuristic_position, detect_persistent_ics, find_critical_components,
    handle_congestion,
};
#[cfg(feature = "python")]
pub use feedback_loop::{FeedbackIterationStage, FeedbackRunContext, run_automated_zero_drc};
#[cfg(feature = "python")]
pub use fine_pitch_escape_stage::FinePitchEscapeStage;
#[cfg(feature = "python")]
pub use grid_stage::ClearanceGridStage;
pub use hv_lv_partition_stage::HvLvPartitionStage;
#[cfg(feature = "python")]
pub use layer_assignment_stage::LayerAssignmentStage;
#[cfg(feature = "python")]
pub use net_ordering_stage::NetOrderingStage;
pub use partition_planner::{
    ComponentPinClasses, CreepageDisplacementGroups, ElectricalNet, GroupedCreepagePlan,
    NetTerminal, PartitionCreepageRequirements, PartitionEnvelope, PartitionPlan, PinClassRecord,
    compact_partition_envelopes, compact_partition_envelopes_with_internal_gaps,
    internal_component_creepage_requirements, partition_creepage_requirements,
    plan_component_partitions, plan_creepage_displacement_groups, plan_grouped_creepage_cuts,
};
#[cfg(feature = "python")]
pub use phased_assignment_stage::PhasedAssignmentStage;
#[cfg(feature = "python")]
pub use phased_component_assignment_validator_stage::phased_validator_hv;
pub use pipeline::{PipelineConfig, PipelineRunner, StageOutcome, StageReport};
#[cfg(feature = "python")]
pub use pipeline_route::PipelineRouteStage;
#[cfg(feature = "python")]
pub use placement_validation_stage::PlacementValidationStage;
#[cfg(feature = "python")]
pub use validator_audit::audit_domain_clearance_validator;
// The emission `Via` (private layer pair + `emit_s_expr` as the only
// sexpr-producing API) is re-exported so its `compile_fail` doctest — the
// structural guarantee that the blind/buried/through type token cannot be
// bypassed — is reachable from an external crate. Unconditional (the
// struct itself is pure Rust, pyo3-free): CI's doctest step runs
// `cargo test --doc --no-default-features`, so a python-gated re-export
// would make the guarantee decorative there.
pub use pipeline_route::Via;
#[cfg(feature = "python")]
pub use power_plane_stage::PowerPlaneStage;
pub use preflight_stage::PreflightStage;
#[cfg(feature = "python")]
pub use router_pipeline::RouterPipeline;
#[cfg(feature = "python")]
pub use setup_stage::{DrcOracleSetupStage, NetClassSetupStage};
pub use slot_generation_stage::SlotGenerationStage;
// Ungated (2026-08-20, Option E scaffolding): the `Stage<S>` trait,
// `StageError` and `StageErrorKind` are pure Rust in both configurations
// (the non-python `Stage<S>` simply has no `BoardState` default type
// parameter — the `From<PyErr>` impl stays python-gated inside stage.rs).
// The Rust CLI driver needs them to implement leaf-callback stages for
// `PipelineRunner` without an interpreter.
pub use stage::{Stage, StageError, StageErrorKind};
pub use subprocess_stage::SubprocessStage;
pub use via_validation_stage::{ViaDeduplicationStage, ViaValidationStage};
pub use zone_assignment_stage::ZoneAssignmentStage;
#[cfg(feature = "python")]
pub use zone_aware_slot_generation_stage::ZoneAwareSlotGenerationStage;
#[cfg(feature = "python")]
pub use zone_geometry_stage::ZoneGeometryStage;

#[cfg(feature = "python")]
use pyo3::prelude::*;

#[cfg(feature = "python")]
#[pymodule]
fn temper_orchestration(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(timing::compare_stage, m)?)?;
    m.add_function(wrap_pyfunction!(timing::p95, m)?)?;
    m.add_function(wrap_pyfunction!(trace_filter::filter_decisions, m)?)?;
    m.add_function(wrap_pyfunction!(
        trace_filter::find_rejected_alternative,
        m
    )?)?;
    m.add_function(wrap_pyfunction!(feasibility::is_converged, m)?)?;
    m.add_function(wrap_pyfunction!(feasibility::component_area_ratio, m)?)?;
    m.add_function(wrap_pyfunction!(feasibility::proximity_rule_impossible, m)?)?;
    m.add_function(wrap_pyfunction!(feasibility::zone_over_capacity, m)?)?;
    m.add_function(wrap_pyfunction!(feasibility::loop_area_violation, m)?)?;
    m.add_function(wrap_pyfunction!(
        feasibility::isolation_barrier_too_large,
        m
    )?)?;
    m.add_function(wrap_pyfunction!(feasibility::derive_emi_max_dist, m)?)?;
    m.add_function(wrap_pyfunction!(feasibility::derive_thermal_clearance, m)?)?;
    m.add_function(wrap_pyfunction!(
        feasibility::derive_si_max_placement_dist,
        m
    )?)?;
    m.add_function(wrap_pyfunction!(
        feasibility::mains_voltage_to_class_code,
        m
    )?)?;
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
    m.add_function(wrap_pyfunction!(config_attach_stage::run_config_attach, m)?)?;
    m.add_function(wrap_pyfunction!(net_ordering_stage::run_net_ordering, m)?)?;
    m.add_function(wrap_pyfunction!(setup_stage::run_drc_oracle_setup, m)?)?;
    m.add_function(wrap_pyfunction!(setup_stage::run_net_class_setup, m)?)?;
    m.add_function(wrap_pyfunction!(zone_geometry_stage::run_zone_geometry, m)?)?;
    m.add_function(wrap_pyfunction!(
        zone_assignment_stage::run_zone_assignment,
        m
    )?)?;
    m.add_function(wrap_pyfunction!(
        slot_generation_stage::run_slot_generation,
        m
    )?)?;
    m.add_function(wrap_pyfunction!(grid_stage::run_clearance_grid_stage, m)?)?;
    m.add_function(wrap_pyfunction!(grid_hv::run_hv_pad_set, m)?)?;
    m.add_function(wrap_pyfunction!(grid_fence::run_grid_fence_check, m)?)?;
    m.add_function(wrap_pyfunction!(grid_fence::run_grid_perf_budget, m)?)?;
    m.add_function(wrap_pyfunction!(
        component_assignment_stage::run_component_assignment,
        m
    )?)?;
    m.add_function(wrap_pyfunction!(
        component_assignment_stage::run_component_assignment_kernel,
        m
    )?)?;
    m.add_function(wrap_pyfunction!(
        phased_component_assignment_validator_stage::run_phased_validator_hv,
        m
    )?)?;
    m.add_function(wrap_pyfunction!(
        zone_aware_slot_generation_stage::run_zone_aware_slot_generation,
        m
    )?)?;
    m.add_function(wrap_pyfunction!(
        phased_assignment_stage::run_phased_assignment,
        m
    )?)?;
    m.add_function(wrap_pyfunction!(
        phased_assignment_stage::run_phase_select_best_slot,
        m
    )?)?;
    m.add_function(wrap_pyfunction!(
        drc_validation_stage::run_drc_validation,
        m
    )?)?;
    m.add_function(wrap_pyfunction!(
        connectivity_validation_stage::run_connectivity_validation,
        m
    )?)?;
    m.add_function(wrap_pyfunction!(
        via_validation_stage::run_via_validation,
        m
    )?)?;
    m.add_function(wrap_pyfunction!(
        via_validation_stage::run_via_deduplication,
        m
    )?)?;
    m.add_function(wrap_pyfunction!(drc_sweep_stage::run_drc_sweep, m)?)?;
    m.add_function(wrap_pyfunction!(
        drc_sweep_stage::run_track_deduplication,
        m
    )?)?;
    m.add_function(wrap_pyfunction!(
        drc_sweep_stage::run_short_circuit_detection,
        m
    )?)?;
    m.add_function(wrap_pyfunction!(
        placement_validation_stage::run_placement_validation,
        m
    )?)?;
    m.add_function(wrap_pyfunction!(
        courtyard_check_stage::run_courtyard_check,
        m
    )?)?;
    m.add_function(wrap_pyfunction!(
        fine_pitch_escape_stage::run_fine_pitch_escape,
        m
    )?)?;
    m.add_function(wrap_pyfunction!(
        hv_lv_partition_stage::run_hv_lv_partition,
        m
    )?)?;
    m.add_function(wrap_pyfunction!(power_plane_stage::run_power_plane, m)?)?;
    m.add_function(wrap_pyfunction!(
        layer_assignment_stage::run_layer_assignment,
        m
    )?)?;
    m.add_function(wrap_pyfunction!(
        apply_placements_stage::run_apply_placements,
        m
    )?)?;
    m.add_function(wrap_pyfunction!(clearance::get_clearance_py, m)?)?;
    m.add_function(wrap_pyfunction!(clearance::run_clearance_check, m)?)?;
    m.add_function(wrap_pyfunction!(clearance::run_creepage_check, m)?)?;
    m.add_function(wrap_pyfunction!(
        clearance::classify_domain_partition_py,
        m
    )?)?;
    m.add_function(wrap_pyfunction!(
        clearance::project_onto_barrier_axis_py,
        m
    )?)?;
    m.add_function(wrap_pyfunction!(
        clearance::evaluate_isolator_feasibility_py,
        m
    )?)?;
    m.add_function(wrap_pyfunction!(
        clearance::domain_clearance_constraints_py,
        m
    )?)?;
    m.add_function(wrap_pyfunction!(clearance::keepaway_constraints_py, m)?)?;
    m.add_function(wrap_pyfunction!(
        clearance::intra_footprint_conflicts_py,
        m
    )?)?;
    m.add_function(wrap_pyfunction!(clearance::audit_domain_clearance_py, m)?)?;
    m.add_function(wrap_pyfunction!(
        netclass::netclass_resolve_component_class_py,
        m
    )?)?;
    m.add_function(wrap_pyfunction!(
        netclass::netclass_separated_constraints_py,
        m
    )?)?;
    m.add_function(wrap_pyfunction!(
        netclass::netclass_separated_constraints_with_creepage_py,
        m
    )?)?;
    m.add_function(wrap_pyfunction!(
        netclass::netclass_creepage_violations_py,
        m
    )?)?;
    m.add_function(wrap_pyfunction!(
        netclass::netclass_creepage_neighborhood_candidates_py,
        m
    )?)?;
    m.add_function(wrap_pyfunction!(
        netclass::netclass_creepage_requirements_py,
        m
    )?)?;
    m.add_function(wrap_pyfunction!(
        partition_planner::plan_component_partitions_py,
        m
    )?)?;
    m.add_function(wrap_pyfunction!(
        partition_planner::partition_creepage_requirements_py,
        m
    )?)?;
    m.add_function(wrap_pyfunction!(
        partition_planner::internal_component_creepage_requirements_py,
        m
    )?)?;
    m.add_function(wrap_pyfunction!(
        partition_planner::plan_grouped_creepage_cuts_py,
        m
    )?)?;
    m.add_function(wrap_pyfunction!(
        partition_planner::plan_creepage_territories_py,
        m
    )?)?;
    m.add_function(wrap_pyfunction!(
        partition_planner::plan_creepage_displacement_groups_py,
        m
    )?)?;
    m.add_function(wrap_pyfunction!(
        partition_planner::plan_creepage_repair_frontier_py,
        m
    )?)?;
    m.add_function(wrap_pyfunction!(
        partition_planner::normalize_stripped_creepage_py,
        m
    )?)?;
    m.add_function(wrap_pyfunction!(
        partition_planner::verify_stripped_creepage_py,
        m
    )?)?;
    m.add_function(wrap_pyfunction!(
        creepage_lower_bounds::analyze_creepage_lower_bounds_py,
        m
    )?)?;
    m.add_function(wrap_pyfunction!(
        partition_planner::compact_partition_envelopes_py,
        m
    )?)?;
    m.add_function(wrap_pyfunction!(channel_mapping::run_channel_mapping, m)?)?;
    m.add_function(wrap_pyfunction!(
        channel_mapping::run_fallback_channel_path,
        m
    )?)?;
    m.add_function(wrap_pyfunction!(
        channel_mapping::run_validated_two_pad_terminals,
        m
    )?)?;
    m.add_function(wrap_pyfunction!(
        channel_mapping::run_expand_all_pad_tree,
        m
    )?)?;
    m.add_function(wrap_pyfunction!(channel_mapping::run_assign_layer, m)?)?;
    m.add_function(wrap_pyfunction!(
        channel_mapping::run_channel_widths_edt,
        m
    )?)?;
    m.add_function(wrap_pyfunction!(pipeline_route::run_select_sat_nets, m)?)?;
    m.add_function(wrap_pyfunction!(
        pipeline_route::run_build_clause_origin,
        m
    )?)?;
    m.add_function(wrap_pyfunction!(
        pipeline_route::run_select_routing_grids,
        m
    )?)?;
    m.add_function(wrap_pyfunction!(pipeline_route::run_next_tstamp, m)?)?;
    m.add_function(wrap_pyfunction!(
        pipeline_route::run_to_stage0_netclass_rules,
        m
    )?)?;
    m.add_function(wrap_pyfunction!(
        pipeline_route::run_write_route_segments,
        m
    )?)?;
    m.add_function(wrap_pyfunction!(
        pipeline_route::run_summarize_batch_results,
        m
    )?)?;
    // Unit U-H (E6 follow-on): the residual _adapter_convert.py adapter
    // marshalling -- the router input/output wire-format construction.
    m.add_function(wrap_pyfunction!(
        pipeline_route::run_collect_pad_positions,
        m
    )?)?;
    m.add_function(wrap_pyfunction!(
        pipeline_route::run_build_route_payload,
        m
    )?)?;
    m.add_function(wrap_pyfunction!(
        pipeline_route::run_build_routing_result,
        m
    )?)?;
    // Phase C residual (append-only per the U4 dispatch): the pipeline
    // contract tail — dag / bottleneck / metrics.
    m.add_class::<dag::StageEvent>()?;
    m.add_class::<dag::PipelineExecutionLog>()?;
    m.add_class::<bottleneck::BottleneckNetEntry>()?;
    m.add_class::<bottleneck::BottleneckRegion>()?;
    m.add_class::<bottleneck::CongestionHeatmapData>()?;
    m.add_class::<bottleneck::BottleneckReport>()?;
    m.add_class::<bottleneck::DeclaredArtifact>()?;
    m.add_class::<metrics::MetricsObserver>()?;
    m.add(
        "CrossValidationError",
        m.py().get_type::<metrics::CrossValidationError>(),
    )?;
    m.add(
        "CanaryCheckError",
        m.py().get_type::<metrics::CanaryCheckError>(),
    )?;
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
    // Orchestration-port unit U-F (append-only per the U-F dispatch): the
    // AutomatedZeroDRC feedback loop (the iterate-until-clean sequencing of
    // deterministic/feedback/orchestrator.py). The orchestrator shim's
    // run() delegates here; the per-iteration call-backs (pipeline.run,
    // drc_runner, parse, mapper, adjuster, config marshalling) stay Python.
    m.add_function(wrap_pyfunction!(feedback_loop::run_automated_zero_drc, m)?)?;
    // Orchestration-port unit U-I (append-only per the U-I dispatch): the
    // CP-SAT placement-loop orchestration -- the legacy classifier loop and
    // the gate-driven loop sequencing plus the solve_with_delta / solve_phase2
    // kernels. The `_loop_core.py` mixin delegates run()/`_run_with_gates`/
    // `_solve_with_delta`/`_solve_phase2` here; the CP-SAT solve, routing,
    // classifier and the gate/field leaf helpers stay Python call-backs.
    m.add_function(wrap_pyfunction!(cpsat_loop::cpsat_run_legacy_loop, m)?)?;
    m.add_function(wrap_pyfunction!(cpsat_loop::cpsat_run_gated_loop, m)?)?;
    m.add_function(wrap_pyfunction!(cpsat_loop::cpsat_solve_with_delta, m)?)?;
    m.add_function(wrap_pyfunction!(cpsat_loop::cpsat_solve_phase2, m)?)?;
    // Orchestration-port unit U-I (append-only per the U-I dispatch): the
    // feedback-classifier DECISION sequencing. The `feedback.py` shim's
    // `classify()` delegates here; congestion handling is Rust-owned and the
    // remaining constraint-building handlers retain Python-object seams.
    m.add_function(wrap_pyfunction!(feedback::classify_feedback, m)?)?;
    // Keep the scalar helper adjacent to its classifier registration so the
    // Python shim cannot observe a partially wired feedback surface.
    m.add_function(wrap_pyfunction!(feedback::handle_congestion, m)?)?;
    // Keep the scalar helper adjacent to its classifier registration so the
    // Python shim cannot observe a partially wired feedback surface.
    m.add_function(wrap_pyfunction!(feedback::compute_heuristic_position, m)?)?;
    m.add_function(wrap_pyfunction!(feedback::find_critical_components, m)?)?;
    m.add_function(wrap_pyfunction!(feedback::detect_persistent_ics, m)?)?;
    // Orchestration-port unit U-I (append-only per the U-I dispatch): the
    // validator-aligned R24 post-solve audit sequencing. The
    // `validator_audit.py` shim's `audit_domain_clearance_validator()`
    // delegates here; `build_validator_placement`, the pad-schema
    // serialization and `verify_iec60335_compliance` stay Python call-backs.
    m.add_function(wrap_pyfunction!(
        validator_audit::audit_domain_clearance_validator,
        m
    )?)?;
    Ok(())
}

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    #[cfg_attr(test, test)]
    fn module_exports_exist() {
        // Compile-time sanity: the exported timing name exists on its
        // modules. The behavioural proof is the differential suite.
        let _ = super::timing::compare_stage(0.0, 1.0, 0.2, 10.0);
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] =
        &[("tests::module_exports_exist", module_exports_exist)];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}
