---
title: Rust Orchestration Engine — Stage trait + phased pipeline migration (32.5k+ numpy orchestration → temper-orchestration)
type: feat
date: 2026-08-09
topic: rust-orchestration-engine
artifact_contract: ce-unified-plan/v1
artifact_readiness: requirements-only
execution: code
product_contract_source: ce-brainstorm
status: draft
swept: null
swept_basis: null
---

# Rust Orchestration Engine — Plan

## Goal Capsule

**Objective:** Define the Rust `Stage` trait, the `Pipeline` executor, and a
phased migration program that moves the 51,727-LOC migration-able Python
orchestration surface (per the 2026-08-09 interrogation:
`docs/evidence/2026-08-09-python-over-rust-interrogation.md`) into the
`temper-orchestration` crate, with Python shrinking to thin entry points.

The Python orchestration surface breaks into two classes the program attacks
in dependency order:

1. **Marshalling boundary** (4,212 LOC) — pure tax: the flat dicts/arrays
   shuttled between Python objects and Rust kernels become Rust-side typed
   structs the kernels take directly.
2. **Orchestration glue** (47,515 LOC) — real control flow (stage sequencing,
   batching, gate logic, model building) calling Rust kernels. The migration
   endpoint is a Rust `Stage` engine where each Python `Stage.run()` becomes a
   single FFI call to the Rust pipeline.

The program reuses the established migration pattern: every migrated module
gets a differential oracle, PBT, metamorphic tests, induction proof, and
behavioral+performance A/B (Wave-4 discipline contract, G1–G8). The ortools
CP-SAT boundary, pydantic, CLI/viz, and subprocess wrappers stay Python
(11,219 LOC + ~1,311 ortools-only — per the interrogation §4).

**Product authority:** temper-orchestration + temper-placer maintainers. The
ortools boundary's KEEP verdict (Phase 1 spike,
`docs/evidence/2026-08-01-ortools-cpsat-spike.md`) is not reopened here.

**Open blockers:** the marshalling types must be created in Rust before the
orchestration can call kernels directly (Phase A → Phase C dependency). The
Board/Netlist types are still Python dataclasses (Phase 2 residual decisions:
`board.py` and `netlist.py` are JUSTIFIED-KEEP pending Phase 3 formats
migration). This plan defines the Rust `BoardState` as a phased struct that
grows fields as their types land in Rust — the `Stage` trait does not block on
every field being typed.

---

## Product Contract

### Summary

The interrogation finds that of the 69,343 LOC of Python-with-Rust-imports,
only 9.2% is delegation shims. The dominant class — 68.5% — is real
orchestration that calls Rust kernels for compute and keeps control flow in
Python. The migration program's "compute in Rust, Python keeps its public API"
end-state was achieved per-kernel, not per-pipeline. This plan makes it
per-pipeline.

The end-state: `temper-orchestration` grows a real `Pipeline`/`Stage` engine.
Each deterministic stage and router_v6 check becomes a Rust `Stage`
implementation. The Python `Pipeline.run()` becomes a thin wrapper that
crosses FFI once per stage (or once per pipeline, once the pipeline executor
itself is in Rust). The 47k LOC of Python orchestration shrinks to ~5–8k LOC
of Rust (the interrogation's Rust expansion estimate) plus thin Python shims.

### Key Decisions

- **D1. The `Stage` trait is the migration interface, not `BoardState`**
  (plan-settled). The Python `Stage(ABC).run(BoardState) -> BoardState`
  pattern maps directly to a Rust trait. The trait is generic over a `State`
  parameter so it can be tested independently of `BoardState`'s full type
  graph. The `PipelineRunner` sequences `Box<dyn Stage<State = BoardState>>`
  instances. This follows the existing Python pattern exactly — a stage
  receives immutable input and returns (possibly-copied) output — while
  allowing the Rust side to use `Rc`/`Arc` for zero-copy sharing (the Python
  `BoardState` is a `frozen=True` dataclass, read-only by convention; Rust
  can enforce that mechanically).

- **D2. `BoardState` is a phased Rust struct, not a single Big Bang**
  (plan-settled). The Python `BoardState` has ~25 fields with types spread
  across 15+ modules — most are Python dataclasses, not yet Rust types.
  Requiring every field to be a typed Rust struct before any stage moves
  would block the orchestration engine behind the marshalling phase. Instead:
  (a) The `BoardState` struct starts with `Option<Py<PyAny>>` for
  unmigrated-type fields (the `Py<PyAny>` escape hatch, consistent with the
  contracts-as-pyclasses pattern from Phase 2). (b) As Phase A marshalling
  types land, their `Py<PyAny>` fields are tightened to typed structs.
  (c) A field's type is tightened in the same PR that migrates the stage that
  reads it — the type is never tightened speculatively.

- **D3. Marshalling must precede orchestration (Phase A → Phase C dependency)**
  (plan-settled). The interrogation ranks marshalling as the highest-value/
  lowest-risk LOC removal. It is also the prerequisite for the Rust stage
  engine to call kernels without round-tripping through Python dicts. A stage
  migrated before its data types exist in Rust would need to marshal from
  `Py<PyAny>` in the stage body — doubling the work. So the program phases
  are dependency-ordered: Phase A (marshalling types) → Phase B (shim
  collapse) → Phases C/D/E (orchestration slices).

- **D4. The ortools boundary stays Python; everything upstream of it migrates**
  (plan-settled, per the Phase 1 spike's KEEP verdict). The interrogation
  confirms `fixed_copper.py` (1,246 LOC) has no ortools import — it builds
  typed geometry/model structs, not ortools calls. It migrates ahead of the
  boundary. `_encoder_solve.py` (717 LOC) and `model.py` (518 LOC) stay
  Python — they contain the actual ortools `CpSolver` calls.

- **D5. The shim-collapse phase (B) is API-freeze, not API-delete**
  (plan-settled). The 6,397 LOC of delegation shims are load-bearing API
  surface: `geometry/primitives.foo` has 8+ production callers and the
  differential tests import the Python names. Collapsing the bodies to
  `.pyi` stubs or `foo = _rust.foo` one-liners preserves the names while
  removing the FFI-tax prose. The extension-absent fallback of the few shims
  that carry one (`router_v6/astar_core_rust.py`) is also preserved.

- **D6. Each phase is pulled independently under the gated roadmap (R5)**
  (plan-settled, per the Wave-4 plan's governance). This plan defines the
  full path; the discipline contract's gate suite (G1–G8) applies to every
  migration PR within each phase.

### Requirements

- **R1.** The `Stage` trait must support the existing Python `Stage(ABC)`
  contract: `name`, `invariants`, `declared_writes`/`declared_reads`,
  `is_active`, and `run(state) -> state`. The Rust trait adds an explicit
  error return: `Result<State, StageError>` (the Python `run()` raises
  exceptions; Rust surfaces them as `Err(StageError)`).

- **R2.** The `PipelineRunner` must sequence stages in declaration order,
  respecting `is_active`, collecting stage errors into a report, and
  supporting observer hooks (for progress/metrics — the Python
  `MetricsObserver` / `ProgressCallback` pattern). The runner itself must not
  depend on any unmigrated Python type.

- **R3.** Every migrated module must clear the Wave-4 gate set (G1–G8): TDD
  differential-oracle-first, behavioral A/B, performance A/B, PBT (>=5
  non-vacuous properties), metamorphic testing (>=3 invariant relations per
  module), induction proof, Rust best-practices bar, and R24 physics
  discipline (N/A for non-physics surfaces).

- **R4.** The marshalling types (Phase A) must be created in their
  consuming crate (not in a new crate). The established pattern:
  `temper-drc-rs` owns DRC validation types, `temper-design-bundle` owns
  design contract types, `temper-io-types` owns KiCad wire types. No new
  "types-only" crate.

- **R5.** The Python public API is preserved throughout. Every migrated
  module keeps a Python shim that re-exports the Rust entity. No consumer
  sees a breaking change. The `__all__` lists, import paths, and class names
  are unchanged.

- **R6.** The Phase-1 deliverable (convergence module migration) must be
  implementable in a single PR by a follow-up agent against the plan's
  specified API. This means: the `Stage` trait and `PipelineRunner` are
  defined in the same PR (they're small; the runner is ~50 LOC of pure-Rust
  sequencing), and the `ConvergenceChecker` is the first concrete `Stage` on
  the new engine.

---

## The Stage-Engine Contract

### The `Stage` trait (Rust signature)

```rust
// packages/temper-orchestration/src/stage.rs

use std::borrow::Cow;

/// A single pipeline stage that transforms a typed state.
///
/// Mirror of Python `deterministic.stages.base.Stage(ABC)`.
/// Generic over `S` so the trait can be tested against
/// trivial state types before `BoardState` is fully typed.
pub trait Stage<S = BoardState> {
    /// Human-readable stage name (used in reports/traces).
    fn name(&self) -> Cow<'static, str>;

    /// Optional DRC invariants this stage must satisfy.
    /// Default empty — most stages have no invariants.
    fn invariants(&self) -> &[InvariantSpec] { &[] }

    /// Bounding boxes of regions this stage modified, if known.
    /// Used by incremental DRC to skip re-checking untouched areas.
    fn last_modified_regions(&self) -> Option<&[(f64, f64, f64, f64)]> { None }

    /// Artifacts this stage promises to produce.
    /// Used by the artifact-contract checker (bottleneck_report.py).
    fn declared_writes(&self) -> &[DeclaredArtifact] { &[] }

    /// Artifacts this stage requires from prior stages.
    fn declared_reads(&self) -> &[DeclaredArtifact] { &[] }

    /// Whether this stage runs in the current pipeline configuration.
    /// When `false`, the runner skips the stage AND its contract obligations.
    fn is_active(&self) -> bool { true }

    /// Execute the stage and return the new state.
    ///
    /// # Errors
    ///
    /// Returns `Err(StageError)` if the stage cannot complete —
    /// a hard failure that halts the pipeline unless the runner
    /// is configured to continue-on-error.
    fn run(&self, state: S) -> Result<S, StageError>;
}
```

### Supporting types

```rust
// packages/temper-orchestration/src/stage.rs (continued)

/// A named pipeline invariant (DRC fence contract).
///
/// Mirror of Python `validation.drc_fence.InvariantSpec`.
#[derive(Debug, Clone)]
pub struct InvariantSpec {
    pub name: String,
    pub description: String,
    pub severity: InvariantSeverity,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum InvariantSeverity { Error, Warning }

/// A contract artifact: something a stage produces or consumes.
///
/// Mirror of Python `pipeline.bottleneck_report.DeclaredArtifact`.
#[derive(Debug, Clone)]
pub struct DeclaredArtifact {
    pub name: String,
    pub artifact_type: String,
}

/// A stage-level error.
///
/// Python `Stage.run()` raises exceptions; Rust surfaces them
/// as `Err(StageError)` so the `PipelineRunner` can collect
/// multiple errors into a report.
#[derive(Debug, Clone)]
pub struct StageError {
    pub stage_name: String,
    pub message: String,
    pub kind: StageErrorKind,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum StageErrorKind {
    /// A recoverable warning — runner may continue.
    Warning,
    /// A hard failure — runner halts by default.
    Fatal,
    /// The stage detected an infeasible constraint set.
    Infeasible,
}
```

### The `BoardState` struct (phased)

```rust
// packages/temper-orchestration/src/board_state.rs
//
// Phase A field-tightening convention:
//   - `Option<Py<PyAny>>` = unmigrated type (Phase A pending)
//   - `Option<TypedStruct>`    = marshalling type landed

use pyo3::PyAny;
use std::collections::HashSet;

/// Immutable snapshot of the board at a pipeline point.
///
/// Mirror of Python `deterministic.state.BoardState`.
/// Fields are `Option` because the pipeline populates them
/// incrementally across stages; a stage that reads a field
/// asserts it is `Some` or returns `Err(StageError)`.
#[derive(Clone)]
pub struct BoardState {
    // ---- Already-migrated or trivial types ----
    pub net_order: Vec<String>,

    // ---- Marshalling-pending (Phase A): `Py<PyAny>` ----
    pub board: Option<pyo3::Py<PyAny>>,
    pub netlist: Option<pyo3::Py<PyAny>>,
    pub loops: Option<pyo3::Py<PyAny>>,
    pub grid: Option<pyo3::Py<PyAny>>,
    pub drc_oracle: Option<pyo3::Py<PyAny>>,
    pub drc_violations: Option<pyo3::Py<PyAny>>,
    pub design_rules: Option<pyo3::Py<PyAny>>,
    pub connectivity_violations: Option<pyo3::Py<PyAny>>,
    pub placement_violations: Option<pyo3::Py<PyAny>>,
    pub placements: Option<pyo3::Py<PyAny>>,    // frozenset of placements
    pub used_slots: Option<pyo3::Py<PyAny>>,     // frozenset of slot ids
    pub config: Option<pyo3::Py<PyAny>>,
    pub component_domain_map: Option<pyo3::Py<PyAny>>,
    pub routing_corridors: Option<pyo3::Py<PyAny>>,
    pub domain_regions: Option<pyo3::Py<PyAny>>,
    pub routes: Option<pyo3::Py<PyAny>>,
    pub vias: Option<pyo3::Py<PyAny>>,
    pub violations: Option<pyo3::Py<PyAny>>,
    pub zones: Option<pyo3::Py<PyAny>>,
    pub component_zone_map: Option<pyo3::Py<PyAny>>,
    pub zone_slots: Option<pyo3::Py<PyAny>>,
    pub layer_assignments: Option<pyo3::Py<PyAny>>,
}

impl BoardState {
    /// Create an empty state — all fields `None`.
    pub fn new() -> Self { /* ... */ }

    /// Convenience: builder pattern for tests.
    pub fn with<T: Into<pyo3::Py<PyAny>>>(mut self, _value: T) -> Self {
        // Setter per field via a typed builder — deferred to implementation
        self
    }
}
```

**Tightening rule**: a `Py<PyAny>` field is promoted to a typed struct
(`Option<ClearanceGrid>`, `Option<HashSet<Placement>>`, etc.) in the *same* PR
that migrates the first Rust `Stage` that reads it. The field-type change is
never a standalone PR — it rides with a consumer so the type is verified live.

### The `PipelineRunner`

```rust
// packages/temper-orchestration/src/pipeline.rs

use crate::stage::{Stage, StageError, StageErrorKind};

/// Observability hook called between stages.
///
/// Mirror of Python `pipeline.metrics_observer.MetricsObserver`
/// and `pipeline.visualization.ProgressCallback`.
pub trait PipelineObserver<S> {
    fn on_stage_start(&mut self, stage_name: &str, state: &S);
    fn on_stage_complete(&mut self, stage_name: &str, result: &Result<S, StageError>, elapsed_ms: f64);
}

/// Result of a full pipeline run.
#[derive(Debug)]
pub struct PipelineReport {
    pub stage_reports: Vec<StageReport>,
    pub total_elapsed_ms: f64,
    pub halted_early: bool,
}

#[derive(Debug)]
pub struct StageReport {
    pub name: String,
    pub elapsed_ms: f64,
    pub outcome: StageOutcome,
}

#[derive(Debug)]
pub enum StageOutcome {
    Completed,
    Skipped,
    Failed(StageError),
}

/// Configuration for pipeline execution.
pub struct PipelineConfig {
    /// If true, a `Fatal` or `Infeasible` error halts the pipeline.
    /// If false, errors are collected and the pipeline continues.
    pub halt_on_error: bool,
}

impl Default for PipelineConfig {
    fn default() -> Self {
        Self { halt_on_error: true }
    }
}

/// Sequences stages and collects reports.
///
/// The runner is NOT generic over `S` in its struct — it stores
/// `Box<dyn Stage<S>>` trait objects. The concrete `S` is `BoardState`
/// for production use, but the runner can be tested with a trivial
/// `S = u32` in unit tests.
pub struct PipelineRunner<S> {
    stages: Vec<Box<dyn Stage<S>>>,
    observers: Vec<Box<dyn PipelineObserver<S>>>,
    config: PipelineConfig,
}

impl<S: Clone> PipelineRunner<S> {
    pub fn new(config: PipelineConfig) -> Self {
        Self { stages: Vec::new(), observers: Vec::new(), config }
    }

    pub fn add_stage(&mut self, stage: Box<dyn Stage<S>>) {
        self.stages.push(stage);
    }

    pub fn add_observer(&mut self, observer: Box<dyn PipelineObserver<S>>) {
        self.observers.push(observer);
    }

    /// Run all stages in declaration order.
    ///
    /// Returns the final state and a report even on error
    /// (the last-successful state is preserved).
    pub fn run(&mut self, initial_state: S) -> (S, PipelineReport) {
        let mut state = initial_state;
        let mut reports = Vec::new();
        let start = std::time::Instant::now();

        for stage in &self.stages {
            if !stage.is_active() {
                reports.push(StageReport {
                    name: stage.name().into_owned(),
                    elapsed_ms: 0.0,
                    outcome: StageOutcome::Skipped,
                });
                continue;
            }

            for obs in &self.observers {
                obs.on_stage_start(&stage.name(), &state);
            }

            let stage_start = std::time::Instant::now();
            let result = stage.run(state.clone());
            let elapsed = stage_start.elapsed().as_secs_f64() * 1000.0;

            for obs in &self.observers {
                obs.on_stage_complete(&stage.name(), &result, elapsed);
            }

            match result {
                Ok(new_state) => {
                    reports.push(StageReport {
                        name: stage.name().into_owned(),
                        elapsed_ms: elapsed,
                        outcome: StageOutcome::Completed,
                    });
                    state = new_state;
                }
                Err(e) => {
                    let is_fatal = matches!(e.kind,
                        StageErrorKind::Fatal | StageErrorKind::Infeasible);
                    reports.push(StageReport {
                        name: stage.name().into_owned(),
                        elapsed_ms: elapsed,
                        outcome: StageOutcome::Failed(e.clone()),
                    });
                    if self.config.halt_on_error && is_fatal {
                        return (state, PipelineReport {
                            stage_reports: reports,
                            total_elapsed_ms: start.elapsed().as_secs_f64() * 1000.0,
                            halted_early: true,
                        });
                    }
                }
            }
        }

        (state, PipelineReport {
            stage_reports: reports,
            total_elapsed_ms: start.elapsed().as_secs_f64() * 1000.0,
            halted_early: false,
        })
    }
}
```

### Error model

- **`StageError`**: every `Stage::run()` returns `Result<S, StageError>`.
  Python `Stage.run()` raised exceptions for hard failures and returned
  `BoardState` for success/warnings. Rust makes the distinction explicit:
  - `StageErrorKind::Warning` — the stage completed but something is worth
    logging (equivalent to Python printing a warning and returning state).
  - `StageErrorKind::Fatal` — the stage cannot complete; pipeline halts if
    `halt_on_error` is true.
  - `StageErrorKind::Infeasible` — a constraints-only variant of Fatal, for
    stages that detect an unsolvable constraint set (e.g., the preflight
    checker's `FAIL` result, the DRC fence validator's fatal violation).

- **Panic safety**: every pyo3 boundary wraps `Stage::run()` in
  `std::panic::catch_unwind`. A Rust panic inside a stage is converted to
  `StageError { kind: Fatal, message: "<panic message>" }` — it never
  unwinds into CPython. (The existing `temper-orchestration` crate already
  sets `profile.release.panic = "unwind"`; the pattern from `timing.rs` is
  reused.)

- **Null-state propagation**: a stage that returns `Err(Fatal)` leaves the
  pipeline state at the last-successful snapshot. The `PipelineReport` records
  which stage failed and why. The Python `run()` wrapper reads the report and
  can re-raise as a Python exception if the caller expects exceptions.

### How a stage calls existing Rust kernels

The established pattern from the per-kernel migration program:

```rust
// Example: migrating setup.py's DRCOracleSetupStage to Rust
use temper_geometry::kicad_transform::rotate_local_to_world_deg;
use temper_drc_rs::constraints_drc_oracle::DRCOracle;
// ... etc.

struct DrcOracleSetupStage {
    design_rules: Option<Py<DesignRules>>,  // Phase 2 pyclass
    parsed_pads: Option<Vec<PadData>>,      // Phase A marshalling type
}

impl Stage<BoardState> for DrcOracleSetupStage {
    fn name(&self) -> Cow<'static, str> {
        "drc_oracle_setup".into()
    }

    fn run(&self, state: BoardState) -> Result<BoardState, StageError> {
        // Direct Rust calls — no PyO3 GIL acquire for the compute path
        let matrix = ClearanceMatrix::new();
        // ... (the body from setup.py lines 52-220, expressed in Rust)

        let oracle = DRCOracle::new(matrix);
        // ... register pads, rebuild index

        let mut new_state = state.clone();
        new_state.drc_oracle = Some(/* pyclass wrapper or Rust struct */);
        Ok(new_state)
    }
}
```

The key: once the types are Rust structs (Phase A), the stage body calls
Rust functions directly — no `Python::with_gil()`, no pyo3 attribute access.
The only FFI crossing is at the pipeline boundary: the Python `run()` shim
constructs the `BoardState` from Python objects, calls
`runner.run(initial_state)`, and converts the final state back to Python
objects for consumers.

---

## Phased Migration

### Dependency ordering

```
Phase A (marshalling → Rust structs)
  └─► Phase B (collapse shims to .pyi/one-liners)
        └─► Phase C (pipeline orchestration)
              └─► Phase D (deterministic stages)
                    └─► Phase E (router_v6 orchestration)
```

Phases C/D/E may partially overlap once Phase A has progressed enough for
the needed types to exist, but the dependency order ensures no stage is
migrated before the types it reads exist in Rust.

### Phase table

| Phase | Scope | LOC (Python removed) | Rust LOC added (est.) | Effort (days) | Risk | Key dependency |
|-------|-------|---------------------:|----------------------:|--------------:|------|----------------|
| **A. Marshalling** | `validation/drc_oracle.py` (marshalers), `validation/drc_runner.py`, `validation/human_reference_extractor.py`, `router_v6/terminal_extraction.py`, `core/hypergraph.py`, `explainability/{decision,trace,serialization,markdown_report}.py`, `core/units.py`, `core/loop_extractor_rs.py`, `deterministic/feedback/{violation_mapper,drc_parser}.py` | 4,212 | 1,500–2,000 | 8–12 | **Low** — pure tax, no control flow | None — the proven netlist/pyclass migration precedent exists |
| **B. Shim collapse** | 57 delegation-shim files (`geometry/{primitives,polygon,sdf,smooth,overlap,transform,projections}.py`, `geometry/__init__.py`, `core/netlist.py`, `core/design_rules.py`, `core/net_types.py`, `core/net_graph.py`, `core/differential_pair.py`, `validation/drc_types.py`, `io/kicad_parser.py`, `io/dsn.py`, `router_v6/astar_core_rust.py`, `requirements/validators/_geometry.py`, `physics/{emi,thermal,safety,inductance}.py`, etc.) | 6,397 | ~0 (`.pyi` stubs) + ~50 (shim bodies) | 3–5 | **Low** — API-freeze only | Phase A not strictly required, but shims are more satisfying when the bodies are gone |
| **C. Pipeline orchestration** | `pipeline/convergence.py`, `pipeline/preflight.py`, `pipeline/derivation.py`, `pipeline/state.py` (PipelineState→PipelineRunner config), `pipeline/dag_expr.py` (delegates to Rust), `pipeline/dag_types.py`, `pipeline/dag_observability.py`, `pipeline/bottleneck_report.py` | 1,550 | 600–900 | 8–12 | **Low-Med** — self-contained, but preflight touches Board/Netlist properties | Phase A types for Board/Netlist/Constraints; Phase 2 pyclasses for VoltageClass, DesignRules |
| **D. Deterministic stage orchestration** | 27 stage files under `deterministic/stages/` (6,252 LOC total — `zone_aware_slot_generation.py` 567, `_grid_stage.py` 416, `setup.py` 250, `placement_validation.py` 293, etc.), plus `deterministic/state.py` (BoardState→Rust struct), `deterministic/bottleneck_map.py`, `deterministic/channels.py`, `deterministic/flags.py`, `deterministic/instrumentation.py`, `deterministic/seed_filter.py` | 7,800 | 3,000–4,500 | 20–30 | **Medium-High** — largest single phase; every stage has its own differential | Phase A (DRC types, placement types) + Phase C (Stage trait + PipelineRunner proven) |
| **E. Router-v6 orchestration** | `router_v6/constraint_model.py` (1,150), `router_v6/net_batching.py` (1,103), `router_v6/clearance_check.py` (833), `router_v6/channel_mapping.py` (639), `router_v6/clearance_engine.py`, `router_v6/creepage_check.py`, `router_v6/fixed_copper.py` (1,246 — in `placer/cp_sat/`), `router_v6/domain_clearance.py`, `router_v6/isolation_barrier.py`, the `_pipeline_route.py` orchestrator, and remaining router_v6 glue. The ortools `_encoder_solve.py` (717) and `model.py` (518) stay Python (ortools boundary, D4). | 16,000–20,000 | 6,000–9,000 | 25–40 | **High** — entangled with ortools boundary, multiprocessing, networkx; biggest surface | Phase A (router types) + Phase D (deterministic state populates router inputs) + petgraph parity pass for bottleneck_geometry (or keep the nx→petgraph bridge) |
| **Residual** | networkx-bound (4,859), kiutils-bound (4,665), shapely-bound (6,027), scipy-bound (1,361) — the interrogation's "blocked" rows | 14,995 | 5,000–7,000 | 15–25 | **Medium-High** — each requires a parity pass or a JUSTIFIED-KEEP verdict | Per-library parity spikes, recorded in the Wave-4 residual catalog |

**Total migration-able**: 51,727 LOC Python removed → ~16,000–24,000 LOC Rust added (the interrogation's Rust expansion estimate: orchestration Rust is ~3–5× denser than Python). Total effort: 74–124 days (interleaved with board path per R5 governance).

### Phase A detail — marshalling types

**What Python is removed**: the `_X_to_board_dict` / `_constraints_to_dict` /
`_placement_to_oracle_dict` marshalers — 4,212 LOC of flat-dict-building
functions that exist only because the Rust kernels accept flat arrays/lists
instead of typed structs.

**What Rust gains**: typed structs in the consuming crates:

| Marshaler (Python) | Host crate | Rust type |
|---|---|---|
| `validation/drc_oracle.py` (712, `_placement_to_board_dict` + `_constraints_to_dict` + `_constraint_value_to_plain`) | `temper-drc-rs` | `DrcBoardSnapshot`, `ConstraintSet`, `ConstraintValue` |
| `validation/drc_runner.py` (476, same marshalers + CheckRunner) | `temper-drc-rs` | `CheckRunner` (moved from Python `dataclass` to Rust struct) |
| `validation/human_reference_extractor.py` (610, `_netlist_to_oracle_dict` / `_placement_to_oracle_dict`) | `temper-drc-rs` | `OracleInput`, `OracleOutput` |
| `router_v6/terminal_extraction.py` (97, `_pin_wire` / `_component_wire` / `_stackup_layer_wire`) | `temper-design-bundle` | `PinWire`, `ComponentWire`, `StackupLayerWire` |
| `core/hypergraph.py` (148, COO triplets + numpy→lists) | `temper-design-bundle` | `Hypergraph` (already has kernel; add typed I/O) |
| `explainability/{decision,trace,serialization,markdown_report}.py` (886) | `temper-orchestration` | `Decision`, `Trace`, `MarkdownReport` |
| `core/units.py` (191) | `temper-geometry` | `Mm`, `Mil`, `Inch` (newtype wrappers over f64) |
| `core/loop_extractor_rs.py` (178) | `temper-design-bundle` | `LoopExtractionInput`, `LoopExtractionOutput` |
| `deterministic/feedback/{violation_mapper,drc_parser}.py` | `temper-drc-rs` | `Violation`, `DrcReport` |

**How the Python shim shrinks**: a marshaler like `_placement_to_board_dict`
currently builds a `dict[str, list[float]]` wire format, passes it to
`temper_drc_rs.check_all_py(...)`. After Phase A, the Rust kernel takes a
`DrcBoardSnapshot` struct directly. The Python shim becomes:
```python
def _placement_to_board_dict(state):  # kept for compat, body collapses
    return _tdrc.DrcBoardSnapshot.from_state(state)
```
The `dict` intermediate disappears.

### Phase C detail — first orchestration slice

| Module | LOC | Migrated to | Python keeps |
|---|---|---|---|
| `pipeline/convergence.py` (391) | `temper-orchestration::convergence` | `TerminationReason`, `ConvergenceCriteria`, `ConvergenceState`, `ConvergenceChecker` | Python shim re-exports all four |
| `pipeline/derivation.py` (118) | `temper-orchestration::derivation` | `derive_constraints_from_spec`, `apply_derived_constraints`, `_mains_voltage_to_class` | Python shim re-exports the two public functions |
| `pipeline/preflight.py` (286) | `temper-orchestration::preflight` | `PreflightChecker`, `PreflightCheck`, `PreflightReport`, `PreflightResult` (+ 10 individual check methods) | Python shim re-exports `PreflightChecker` |
| `pipeline/state.py` (117 — PipelineState) | `temper-orchestration::pipeline` | `PipelineConfig`, `PipelinePhase` | Python keeps `PipelineState` (it's the container for all phases; becomes a thin wrapper around the Rust pipeline runner) |
| `pipeline/dag_expr.py` (201) | `temper-orchestration::dag_expr` | Predicate parser+eval | Python shim (1 DAG-dsl consumer) |
| `pipeline/dag_types.py` (111) | `temper-orchestration::dag_types` | DAG node types | Python shim |
| `pipeline/dag_observability.py` (80) | `temper-orchestration::dag` | Observability hooks | Python shim |
| `pipeline/bottleneck_report.py` (179) | `temper-orchestration::bottleneck` | `DeclaredArtifact`, report formatter | Python shim |
| `pipeline/metrics_observer.py` (176) | `temper-orchestration::metrics` | `MetricsObserver`, `CanaryCheckError`, `CrossValidationError` | Python shim (used by the pipeline dashboard) |
| `pipeline/explainability.py` (108) | `temper-orchestration::explainability` | Decision trace collected from stages | Python shim |
| `pipeline/visualization.py` (292 — Rich/terminal) | **JUSTIFIED-KEEP** — `click`/`rich` Python-only | — | Stays Python; decorates the Rust pipeline |
| `pipeline/terminal_dashboard.py` (209) | **JUSTIFIED-KEEP** — `rich` | — | Stays Python |

**What Python is removed**: ~1,550 LOC of pipeline orchestration (all of
convergence, derivation, preflight, DAG, bottleneck report, metrics, state
config, explainability). **What stays Python**: `visualization.py`,
`terminal_dashboard.py` (rich/click), and the `__init__.py` public API shim.

### Phase D detail — deterministic stage orchestration

The 6,252 LOC of deterministic stages migrate as Rust `Stage` implementations.
Order within Phase D is by dependency (a stage that reads another stage's
output migrates after the producing stage's types exist):

| Batch | Stages | LOC | Depends on |
|---|---|---|---|
| D1 (setup) | `setup.py` (250), `net_ordering.py` (47), `config_attach.py` | ~350 | Phase A: DRC types, Pad, ClearanceMatrix |
| D2 (zones) | `zone_geometry.py` (105), `zone_assignment.py` (54), `slot_generation.py` (54) | ~213 | D1 (ClearanceGrid populated) |
| D3 (grid) | `_grid_core.py` (482), `_grid_hv.py` (126), `_grid_fence.py` (139), `_grid_stage.py` (416) | 1,163 | D1 |
| D4 (assignment) | `component_assignment.py` (247), `phased_component_assignment.py` (49), `phased_component_assignment_validator.py` (353) | 649 | D2, D3 |
| D5 (zone-aware) | `zone_aware_slot_generation.py` (567), `_phase_core.py` (326), `_phase_zones.py` (410), `_phase_rotation.py` (259), `_phase_validation.py` (195) | 1,757 | D2–D4 |
| D6 (validation) | `placement_validation.py` (293), `via_validation.py` (261), `drc_sweep.py` (257), `drc_validation.py` (72), `connectivity_validation.py` (145), `courtyard_check.py` (192) | 1,220 | D4+D5 (placements populated) |
| D7 (routing-adjacent) | `fine_pitch_escape.py` (319), `hv_lv_partition.py` (181), `power_plane.py` (148), `layer_assignment.py` (79), `apply_placements.py`, `clearance_grid.py` (shim only), `base.py` (retired — replaced by Rust `Stage` trait) | ~830 | D6 |

Each batch is a G4 verification unit: all stages in the batch share one
differential oracle and one corpus, with >=5 PBT properties across the unit
and every module reached by >=1 property.

### Phase E detail — router-v6 orchestration

The router_v6 orchestration migrates constraint-model building, net batching,
and per-net checks whose compute is already all-Rust-kernel. The ortools
boundary stays Python (D4).

| Migration slice | Modules | LOC | What Rust gains |
|---|---|---|---|
| E1 (constraint model) | `router_v6/constraint_model.py` (1,150) | 1,150 | `ModelBuilder::build()` in `temper-design-bundle` |
| E2 (fixed copper) | `placer/cp_sat/fixed_copper.py` (1,246 — verified: no ortools import) | 1,246 | `FixedCopperBuilder` in `temper-design-bundle` |
| E3 (clearance family) | `router_v6/clearance_check.py` (833), `clearance_engine.py`, `creepage_check.py`, `domain_clearance.py`, `isolation_barrier.py` | ~2,500 | Per-check stages in `temper-orchestration` |
| E4 (channel ops) | `router_v6/channel_mapping.py` (639), `channel_widths.py` (694 — shapely-blocked portions stay Python) | ~1,000 | Channel mapping in `temper-orchestration` |
| E5 (net batching) | `router_v6/net_batching.py` (1,103) | 1,103 | Batch loop in `temper-rust-router` |
| E6 (pipeline route) | `router_v6/_pipeline_route.py` (682), `_adapter_convert.py` (1,050) | 1,732 | Pipeline adapter in `temper-orchestration` |
| **Stays Python** | `_encoder_solve.py` (717), `model.py` (518), `unsat.py` | 1,235 | Ortools boundary (KEEP verdict) |
| **Conditional** | `bottleneck_geometry.py` (1,229 — networkx min-cut), `channel_skeleton.py` (626 — shapely Voronoi) | 1,855 | Requires petgraph/geometry parity pass |

---

## Phase-1 Concrete Deliverable

### What ships

The Phase-1 PR migrates one self-contained pipeline module to the Rust
`Stage` engine — the `convergence` module — along with the `Stage` trait,
`PipelineRunner`, and supporting types. This is the smallest tractable slice
that exercises every part of the engine contract.

### Files changed (in the deliverable PR)

**New Rust files** (in `packages/temper-orchestration/src/`):

```
stage.rs          — Stage trait, StageError, InvariantSpec, DeclaredArtifact
pipeline.rs       — PipelineRunner, PipelineReport, StageReport, PipelineObserver
board_state.rs    — BoardState struct (phased, mostly Py<PyAny>)
convergence.rs    — TerminationReason, ConvergenceCriteria, ConvergenceState,
                    ConvergenceChecker (as Stage<ConvergenceState>)
```

**Modified Rust files**:

```
lib.rs            — register modules; add #[pyclass]/#[pyfunction] exports
                    for the Python-visible types
Cargo.toml        — no new dependencies needed (Phase-1 types are std-only)
```

**New Python files**:

```
packages/temper-placer/tests/pipeline/test_convergence_rust_differential.py
  — Differential oracle: verbatim copy of convergence.py's classes,
    committed BEFORE Rust code (G1 TDD), then Rust vs Python comparison
packages/temper-placer/tests/pipeline/test_convergence_pbt.py
  — >=5 PBT properties (G4)
packages/temper-placer/tests/pipeline/test_convergence_metamorphic.py
  — >=3 metamorphic relations (G5)
```

**Modified Python files**:

```
packages/temper-placer/src/temper_placer/pipeline/convergence.py
  — Becomes a delegation shim: re-exports TerminationReason, ConvergenceCriteria,
    ConvergenceState, ConvergenceChecker from temper_orchestration
packages/temper-placer/src/temper_placer/pipeline/__init__.py
  — No change needed (re-exports still resolve to the same names)
```

### Exact API (Python-visible)

```python
# After migration, convergence.py becomes:
from temper_orchestration import (
    ConvergenceChecker,
    ConvergenceCriteria,
    ConvergenceState,
    TerminationReason,
)
__all__ = [
    "TerminationReason",
    "ConvergenceCriteria",
    "ConvergenceState",
    "ConvergenceChecker",
]
```

The four classes have identical constructors, methods, and `__repr__` as the
pre-migration Python dataclasses — validated by the differential oracle.

### Exact API (Rust — implementation detail for the follow-up agent)

```rust
// packages/temper-orchestration/src/convergence.rs
// Exported as pyclasses via #[pyclass] on each type

use pyo3::prelude::*;

/// Mirror of Python `pipeline.convergence.TerminationReason(Enum)`.
#[pyclass(eq, frozen, name = "TerminationReason")]
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum TerminationReason {
    Success,
    MaxIterations,
    Timeout,
    Infeasible,
    NoProgress,
    UserAbort,
    RoutabilityRegression,
    RoutabilityConverged,
}

/// Mirror of Python `pipeline.convergence.ConvergenceCriteria`.
#[pyclass(dict, frozen, name = "ConvergenceCriteria")]
#[derive(Clone, Debug)]
pub struct ConvergenceCriteria {
    #[pyo3(get, set)]
    pub max_iterations: usize,
    #[pyo3(get, set)]
    pub max_refinement_iterations: usize,
    #[pyo3(get, set)]
    pub timeout_seconds: f64,
    #[pyo3(get, set)]
    pub phase_timeout_seconds: f64,
    #[pyo3(get, set)]
    pub max_overlap_mm2: f64,
    #[pyo3(get, set)]
    pub max_boundary_violation_mm: f64,
    #[pyo3(get, set)]
    pub min_routing_completion: f64,
    #[pyo3(get, set)]
    pub min_manufacturing_margin_mm: f64,
    #[pyo3(get, set)]
    pub min_loss_improvement: f64,
    #[pyo3(get, set)]
    pub stagnation_epochs: usize,
}

/// Mirror of Python `pipeline.convergence.ConvergenceState`.
#[pyclass(dict, name = "ConvergenceState")]
#[derive(Clone, Debug)]
pub struct ConvergenceState {
    #[pyo3(get, set)]
    pub iteration: usize,
    #[pyo3(get, set)]
    pub loss_history: Vec<f64>,
    #[pyo3(get, set)]
    pub best_loss: f64,
    #[pyo3(get, set)]
    pub epochs_since_improvement: usize,
    #[pyo3(get, set)]
    pub routing_completion_history: Vec<f64>,
    #[pyo3(get, set)]
    pub best_routability: Option<f64>,
    #[pyo3(get, set)]
    pub stall_count: usize,
    #[pyo3(get, set)]
    pub start_time: Option<f64>,  // timestamp as float seconds
}

/// Mirror of Python `pipeline.convergence.ConvergenceChecker`.
///
/// After migration, this also implements `Stage<BoardState>` for use in
/// the Rust pipeline, though the pyclass API preserves the existing
/// `check()` method for Python consumers during the transition.
#[pyclass(name = "ConvergenceChecker")]
pub struct ConvergenceChecker {
    criteria: ConvergenceCriteria,
}

#[pymethods]
impl ConvergenceChecker {
    #[new]
    fn new(criteria: ConvergenceCriteria) -> Self {
        Self { criteria }
    }

    /// The existing Python API: check(state) -> (TerminationReason, str).
    /// Bit-exact with the pre-migration implementation.
    fn check(&self, state: &ConvergenceState) -> (TerminationReason, String) {
        // ... (the Python body, replicated in Rust)
    }
}

impl Stage<crate::board_state::BoardState> for ConvergenceChecker {
    fn name(&self) -> std::borrow::Cow<'static, str> {
        "convergence_check".into()
    }

    fn run(&self, state: crate::board_state::BoardState) -> Result<crate::board_state::BoardState, crate::stage::StageError> {
        // For Phase-1, the convergence stage reads scalar fields from
        // BoardState (iteration count, timing) but does not modify it.
        // It returns the state unchanged with a convergence verdict
        // attached via a side channel (observer).
        //
        // Full integration with BoardState is deferred to Phase C
        // when PipelineRunner wires convergence into the main loop.
        Ok(state)
    }
}
```

### What the Phase-1 PR does NOT do

- **No deterministic stages are migrated.** The `Stage` trait is proven on
  `ConvergenceChecker` but not yet applied to `DRCOracleSetupStage` etc.
- **No `BoardState` marshalling types are created.** The `BoardState` struct
  exists with `Py<PyAny>` fields as a placeholder; fields are tightened in
  Phase A + subsequent PRs.
- **No `PipelineRunner` integration with the Python `Pipeline.run()` loop.**
  The runner exists in Rust, tested in unit tests; the Python pipeline still
  uses its own sequencing. Wiring the Rust runner into the Python pipeline
  is the first PR of Phase C.
- **No changes to `pipeline/preflight.py`, `derivation.py`, or any other
  module.** Only `convergence.py` is touched.

### Verification gates for Phase-1

| Gate | What | How |
|------|------|-----|
| G1 TDD | Differential oracle committed before Rust | `test_convergence_rust_differential.py` with `_py_oracle_convergence.py` verbatim copy |
| G2 Behavioral A/B | Bit-identical `TerminationReason`, criteria matching, `check()` output | Differential suite: 100+ randomized `ConvergenceState` inputs, bit-exact `==` on the `(reason, message)` tuple |
| G3 Performance A/B | No regression beyond noise (pure-delegation carve-out: the convergence checker is <1ms; overhead is the FFI crossing + pyclass construction) | CI perf-check; stated noise floor in PR body |
| G4 PBT | >=5 non-vacuous properties | Property table in PBT file docstring; vacuity-guarded per property |
| G5 Metamorphic | >=3 invariant relations per module | Stated in PBT/metamorphic file |
| G6 Induction | Non-applicability note (data-only module, no recursive computation) | `VERIFICATION.md` |
| G7 Rust bar | No unwrap outside tests, catch_unwind at pyo3 boundaries, clippy green | CI log |
| G8 R24 physics | N/A — convergence is pure data, no physics | `VERIFICATION.md` |

### PBT property examples (G4)

| Property | Description | Anti-vacuity mutant |
|---|---|---|
| P1 | `ConvergenceState` with `iteration >= max_iterations` → `check()` returns `MaxIterations` | Always-return-Success kernel |
| P2 | `ConvergenceState` with elapsed time > `timeout_seconds` → `Timeout` (within 1ms tolerance for clock jitter) | Always-return-Success kernel |
| P3 | `ConvergenceState` with `best_routability >= min_routing_completion` and no other termination condition → `RoutabilityConverged` | Always-return-MaxIterations kernel |
| P4 | `ConvergenceState` with `epochs_since_improvement >= stagnation_epochs` and non-decreasing loss → `NoProgress` | Stagnation-counter-off-by-one kernel |
| P5 | Multiple termination conditions satisfied simultaneously → deterministic priority order (Timeout > MaxIterations > Infeasible > NoProgress > Routability*) — the *first* match wins | Swapped-priority-order kernel |
| P6 | Empty `loss_history` → no `NoProgress` (can't detect stagnation without history) | Always-detect-stagnation kernel |
| P7 | `check()` never panics on any valid `ConvergenceState` input combination | NaN-infection kernel (set `best_loss = NaN` → should be handled, not panic) |

### Metamorphic relations (G5)

- **MR1 — Monotonic iteration**: Increasing `iteration` while holding all
  other fields constant never flips a termination verdict from `false` to
  `true` (the checker is monotonic in iteration count: if it doesn't fire at
  `iteration = n`, it won't fire at `iteration = n-1`).
- **MR2 — Loss improvement resets stall**: A `ConvergenceState` that would
  trigger `NoProgress` at epoch `n` no longer triggers it if a new loss value
  lower than `best_loss` is appended to `loss_history`.
- **MR3 — Criteria permutation invariance**: Swapping `max_iterations` and
  `max_refinement_iterations` values does not change the `check()` result
  when all other fields are within both limits (the two fields govern
  different checks; a state within both limits is immune to their swap).

---

## Unit Breakdown with Gates (full migration)

The Phase-1 deliverable is U1. Phases A–E decompose into units that follow
the established per-migration pipeline pattern:

| Unit | Phase | Scope | Depends on | Gates |
|------|-------|-------|-----------|-------|
| **U0** (Stage trait) | — | `stage.rs`, `pipeline.rs`, `board_state.rs` — the engine (no migration, pure scaffolding) | None — ships with U1 | G7 (Rust bar) |
| **U1** (convergence) | Phase C | `convergence.py` → `convergence.rs` | U0 | G1–G8 |
| **U2** (derivation) | Phase C | `derivation.py` → `derivation.rs` | Phase A (VoltageClass already Rust; PcbSpecification fields) | G1–G8 |
| **U3** (preflight) | Phase C | `preflight.py` → `preflight.rs` | Phase A (Board/Netlist types) + U0 | G1–G8 |
| **U4** (pipeline state) | Phase C | `pipeline/state.py` PipelineState→Rust config | U0 + U3 | G1–G8 |
| **U5** (marshalling batch 1 — DRC types) | Phase A | `drc_oracle.py`, `drc_runner.py` marshalers | None | G1–G8 per type cluster |
| **U6–U10** | Phase A | Remaining marshalers (5 batches) | U5 | G1–G8 |
| **U11–U13** | Phase B | Shim collapse (3 batches by import graph) | Phase A (shims are more satisfying when bodies are gone; not a hard dependency) | G2 (behavioral A/B: import resolution unchanged), G3 (no perf delta), G7 |
| **U14–U20** | Phase D | Deterministic stage batches D1–D7 | Phase A (types) + U0 (engine) | G1–G8 per batch |
| **U21–U26** | Phase E | Router_v6 batches E1–E6 | Phase A + Phase D (state populated) | G1–G8 per batch |

---

## Risks + Mitigations

### R-A. The `BoardState` phased-struct approach accumulates `Py<PyAny>` debt (Medium)

**Risk:** `BoardState` starts with 20+ `Option<Py<PyAny>>` fields and
tightens incrementally. A stage migrated before its data types land would
need to call `py.getattr()` on `Py<PyAny>` objects — reintroducing the
marshalling tax inside the Rust stage body.

**Mitigation (D2, D3):** Phases are dependency-ordered: no orchestration
stage is migrated before Phase A has created the types it reads. The
`BoardState`'s `Py<PyAny>` fields are tightened in the same PR that migrates
the stage consuming them — the type is never tightened speculatively. If
Phase A stalls, Phase C/D/E do not start on the blocked types.

### R-B. The Rust pipeline diverges from the Python pipeline's duck-typed flexibility (Medium)

**Risk:** The Python `Protocol`-based pipeline (`PipelineStage` Protocol in
`protocol.py`, the `@runtime_checkable` adapter pattern) uses structural
typing — any object with a `.run(state)` method is a stage. The Rust `Stage`
trait replaces this with nominal typing (`impl Stage<BoardState>`). A stage
that currently satisfies the Protocol without extending the `Stage` ABC would
need to be wrapped.

**Mitigation:** The `protocol.py` module is a recorded JUSTIFIED-KEEP
(Phase 2 residual decisions: "structural-typing `@runtime_checkable` Protocol
— a typing construct, not runtime data — no pyclass mapping"). The
orchestration migration does not touch the Protocol layer. The Rust
`PipelineRunner` sequences `Box<dyn Stage<BoardState>>` instances; the Python
adapter layer wraps Rust stages to satisfy the Protocol for the few consumers
that use structural typing. The `Stage` ABC subclasses (which is ALL of
`deterministic/stages/`) migrate directly — they already have nominal typing.

### R-C. The Phase-1 convergence module has no real `BoardState` consumer (Low)

**Risk:** The Phase-1 deliverable migrates `ConvergenceChecker` as a
`Stage<BoardState>` but the checker's `run()` doesn't actually modify
`BoardState` — it reads convergence criteria and returns a verdict. A
reviewer may question whether this proves the `Stage` trait's viability for
real board stages.

**Mitigation:** The Phase-1 deliverable explicitly names this as a
scaffolding step — the `Stage` trait is proven on a trivial implementor to
validate the API shape before real stages (Phase C's U3 preflight, Phase D's
D1 setup) exercise the full `BoardState` read/write path. The Phase-1
deliverable's own scope section states what it does NOT do. U0 (`stage.rs` +
`pipeline.rs`) is pure scaffolding, not a migration — it ships alongside U1
so the engine exists, but its real test is Phase C's preflight stage (the
first stage that reads 4+ `BoardState` fields).

### R-D. The marshalling-to-orchestration handoff creates a coordination bottleneck (Medium)

**Risk:** Phase A's 4,212 LOC of marshalers spread across 5+ crates
(`temper-drc-rs`, `temper-design-bundle`, `temper-geometry`,
`temper-orchestration`) — if the crates' maintainers are different people,
the types need to land in dependency order and the orchestration team is
blocked.

**Mitigation:** The Wave-4 plan's governance (R5) means phases are pulled
independently. Phase A is the first pull; the orchestration team can
contribute to Phase A to unblock their own work. The types are assigned to
the crate that already owns the kernel that consumes them — the crate
maintainer is the natural reviewer. No new crate is created.

### R-E. The `Stage::run()` `Clone` bound is expensive for large `BoardState` (Medium)

**Risk:** The Python `BoardState` is a `frozen=True` dataclass with
`frozenset`s — immutable by convention, cloned via `replace()` for each stage
that modifies a field. The Rust `PipelineRunner` calls
`stage.run(state.clone())`, cloning the entire `BoardState` for every stage.
With 25 fields, some containing `HashSet`s, this could be measurable.

**Mitigation:** The Python pipeline already pays this cost (dataclass
`replace()` copies the whole struct). The Rust `BoardState` can use `Arc`
internally for large fields (the `Py<PyAny>` fields are already `Arc`-like —
`Py<T>` is a reference-counted pointer). If profiling shows the clone is a
bottleneck, the `Stage` trait can be refined to `fn run(&self, state: &S) ->
S` with interior `Arc` sharing, or to `fn run(&self, state: &mut S) ->
Result<(), StageError>` (mutable borrow). The current design preserves the
Python pattern exactly; optimization is deferred to a perf spike gated on
measured regression.

### R-F. The Python team's differential tests import from the Python shim, not the Rust module directly (Low)

**Risk:** After Phase B collapses shims to `X = _rust.X` one-liners, a
differential test that imports `from temper_placer.geometry.primitives import
foo` and also imports the `_py_oracle` copy will be comparing the same Rust
implementation against itself if the shim already points at the Rust module.

**Mitigation:** The G1 TDD gate requires the oracle be a verbatim copy of the
**pre-migration** Python source, committed BEFORE the Rust implementation.
The differential test imports the oracle directly (not through the shim). The
shim's delegation target is the **new** Rust implementation. The two are
distinct by construction. This is the established pattern from all 20+
existing differential test files.

---

## Non-Goals

- **No ortools boundary migration.** The Phase 1 spike's KEEP verdict
  (`docs/evidence/2026-08-01-ortools-cpsat-spike.md`) is not reopened.
  `_encoder_solve.py`, `model.py`, `unsat.py`, and `handlers/*` stay Python.
  `fixed_copper.py` migrates because it has no ortools import (verified in
  the interrogation).
- **No pydantic migration.** `_constraint_types/**`, `validation/prereg/schema.py`,
  `io/config_loader.py` stay Python. Pydantic is a recorded Python-only
  dependency.
- **No CLI/viz migration.** `cli/timing.py`, `cli/trace_commands.py`,
  `pipeline/visualization.py`, `pipeline/terminal_dashboard.py` stay Python
  (click/rich).
- **No subprocess-wrapper migration.** `validation/spice.py` (ngspice),
  `validation/drc.py` (kicad-cli), `validation/preflight.py` (tool calls),
  `placer/cp_sat/gates.py` (kicad-cli) stay Python.
- **No test-suite migration.** The Python test suite retains the differential
  oracles and PBT/metamorphic suites; Rust-side tests cover migrated modules'
  internal logic. The suite's own fate is a Phase 6 decision, outside this plan.
- **No `protocol.py` migration.** The `@runtime_checkable PipelineStage`
  Protocol is a recorded JUSTIFIED-KEEP (Phase 2 residual decisions).
- **No `scripts/` migration.** Top-level tooling is a Phase 6 decision.
- **No visualization/WASM work.** The board renderer is a Phase 6 decision.

---

## Sources

- Interrogation: `docs/evidence/2026-08-09-python-over-rust-interrogation.md`
  (the 69,343-LOC classification, §1–6)
- Wave-4 full-migration program: `docs/plans/2026-08-01-001-feat-wave4-full-migration-program-plan.md`
  (Phase 5 orchestration scope, R1–R8, D1–D6)
- Wave-4 discipline contract: `docs/wave4-discipline-contract.md` (G1–G8
  gate checklist, B1–B13 bit-exactness catalog, R3 residual procedure)
- Phase 1 ortools spike: `docs/evidence/2026-08-01-ortools-cpsat-spike.md`
  (KEEP verdict with blocker corrected 2026-08-04)
- Phase 2 residual decisions: `docs/plans/2026-08-01-001-feat-wave4-full-migration-program-plan.md`
  § "Phase 2 residual decisions" (board/netlist JUSTIFIED-KEEP, net_types MIGRATED, etc.)
- Wave-C contracts migration: `docs/plans/2026-08-08-001-feat-wavec-core-contracts-migration-plan.md`
  (ce-unified-plan/v1 format, U1–U6 unit structure)
- Existing temper-orchestration crate: `packages/temper-orchestration/src/lib.rs`
  (963 LOC, no Stage trait yet — the home for this plan's engine)
- Python Stage ABC: `packages/temper-placer/src/temper_placer/deterministic/stages/base.py`
  (48 LOC, `Stage(ABC)` with `run(BoardState) -> BoardState`)
- Python BoardState: `packages/temper-placer/src/temper_placer/deterministic/state.py`
  (~150 LOC, 25-field frozen dataclass)
- Python pipeline convergence: `packages/temper-placer/src/temper_placer/pipeline/convergence.py`
  (~400 LOC, `TerminationReason`, `ConvergenceCriteria`, `ConvergenceState`,
  `ConvergenceChecker`)
- Python pipeline derivation: `packages/temper-placer/src/temper_placer/pipeline/derivation.py`
  (118 LOC, `derive_constraints_from_spec`, `apply_derived_constraints`)
- Python pipeline state: `packages/temper-placer/src/temper_placer/pipeline/state.py`
  (117 LOC, `PipelineConfig`, `PipelinePhase`, `PipelineError`, `PipelineState`)
- Python preflight: `packages/temper-placer/src/temper_placer/pipeline/preflight.py`
  (286 LOC, `PreflightChecker` with 10 check methods)
- Deterministic stages inventory: `packages/temper-placer/src/temper_placer/deterministic/stages/`
  (27 files, 6,252 LOC total)
- Router-v6 inventory: `packages/temper-placer/src/temper_placer/router_v6/`
  (30,932 LOC total; ~16–20k in scope for Phase E)
- VoltageClass pyclass: `packages/temper-design-bundle/src/net_types.rs`
  (already migrated; derivation can call it directly)
- Bit-exactness precedent: `docs/wave4-discipline-contract.md` §2 (B1–B13
  catalog, dlsym/libm, py_hypot, numpy pairwise sum, etc.)
- Per-migration pipeline: `docs/migration-pipeline.md` (stages 1–6)
