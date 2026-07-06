---
date: 2026-07-01
topic: pipeline-cleanup-observability
focus: "DAG cleanup, logging, observability, profiling, dead code removal, documentation, measurement, testing, formal verification, Rust rewrite"
mode: repo-grounded
continues: 2026-06-28-pipeline-observability-ideation.md
---

# Ideation: Pipeline Cleanup, Observability & Quality Infrastructure

## Grounding Context

### Codebase Context
- Temper: ESP32-S3 induction cooker. Placement pipeline: Placement (JAX NSGA-II) -> Plane Generation -> Routing (Router V6, 4-stage) -> DRC fence.
- Two CLI paths: `optimize` (monolithic, 3500-line legacy) vs `pipeline` (new declarative DAG engine). Two constraint systems coexist: legacy `PlacementConstraints` (1730-line `io/config_loader.py`) and PCL (`pcl/constraints.py`, 752 lines with `loss_bridge.py`).
- **Core bug**: The `optimize` path's PCL auto-discovery looks for `temper_induction_cooker.pcl.yaml`, doesn't find it, silently skips. Keepout constraints, decoupling detection, and tag expansion are never applied. PCL `pcl_validate` CLI and `input_stage` pipeline path DO parse and enrich PCL correctly.
- Dead-code baseline: 115+ entries. 9 `PipelineOrchestrator` methods marked `# pragma: no cover`. No structured logging or profiling.
- Router v6: 80+ files (A*, SAT, Numba).

### Past Learnings
- Declarative Stage DAG replaced monolith (YAML manifest + StageHandler)
- 5-step dead-code deletion playbook: import graph, reverse-topo delete, adapters, port consumers, `git rm`
- Infrastructure-unwired failure mode: 3 components tested/merged but never wired into pipeline
- 4-layer invariant chain: SSOT->post_init->pipeline fence->output validation->Hypothesis->CI gate
- Hypothesis 4-layer test architecture: shared strategies, theorem classes, property decorators
- Observer cross-validation: schema->cross-validate->canary before every JSONL write

### External Context
- OpenROAD/DREAMPlace: single-application, common database, structured logging `[SEVERITY TOOL-ID-MSGID]`
- JAX profiling: `jax.profiler.trace()`, `block_until_ready()`, XProf
- SMT solvers (Z3) for geometric constraint verification
- PyO3+maturin for Rust migration, `nalgebra`, `Rayon`
- MADR ADR specification for architecture decisions
- Dead-code tools: Ruff, Skylos, Deadcode, Vulture

## Topic Axes
1. Pipeline topology & dead-code elimination — DAG structure, dead paths, parallel constraint systems, code removal strategy
2. Observability, profiling & measurement — Structured logging, metrics write path, profiling infrastructure, per-stage measurement
3. Constraint system unification — PCL→loss bridge wiring, keepout/decoupling/tag expansion loss functions, legacy deprecation
4. Testing, formal verification & invariant chains — Hypothesis suites, contract oracles, SMT verification, property-based testing
5. Documentation, ADRs & Rust migration — Architecture decision records, codebase documentation, Rust extraction strategy

## Ranked Ideas

### 1. PCL Single-Source-of-Truth with Hard-Fail Discovery
**Axis:** Constraint system unification
**Description:** Replace `load_constraints()`'s legacy `PlacementConstraints` return with PCL `ConstraintCollection`, delegating to the already-working `pcl_validate`/`input_stage` enrichment path. Flip the silent `.pcl.yaml` auto-discovery skip into a hard diagnostic failure. Once all consumers port, delete the 1730-line `io/config_loader.py`.
**Basis:** `direct:` The `optimize` path's PCL auto-discovery looks for `temper_induction_cooker.pcl.yaml`, doesn't find it, and silently skips. PCL `pcl_validate` CLI and `input_stage` path DO parse and enrich PCL correctly. `direct:` Infrastructure-unwired failure mode documented.
**Rationale:** Eliminates root cause of ISOLATION_BARRIER ghost zone. Unification deletes the decision point by construction.
**Downsides:** Breaking change for boards without `.pcl.yaml` — needs auto-generate stub or `--no-pcl` flag during transition.
**Confidence:** 95% | **Complexity:** Medium | **Status:** Unexplored

### 2. DAG-Native Structured Observability & Profiling Middleware
**Axis:** Observability, profiling & measurement
**Description:** Inject observability as DAG middleware — no manual instrumentation per stage. Every stage gets: structured logging in OpenROAD-style format, JAX `jax.profiler.trace()` wrapping with `block_until_ready()` fences, per-stage canary metrics with CI regression gates. `StageMetrics` emission is mandatory.
**Basis:** `direct:` Every stage uses bare `print()`; no structured logging exists. `direct:` Observer cross-validation pattern already documented but canary check only warns. `external:` JAX profiling + OpenROAD structured logging.
**Rationale:** PCL silent-skip would have been caught by `constraints_active: 0` metric. Profiling data prerequisite to Rust extraction. Every future stage author gets observability for free.
**Downsides:** 5-15% JSONL serialization overhead; needs baseline profiling budgets.
**Confidence:** 85% | **Complexity:** Medium | **Status:** Unexplored

### 3. Systematic Dead-Code Elimination with Zero-Tolerance CI Gate
**Axis:** Pipeline topology & dead-code elimination
**Description:** Execute 5-step reverse-topo deletion playbook against 115+ entries. Priority: 9 `# pragma: no cover` orchestrator methods. CI gate blocks PRs increasing dead-code count. Consolidate Router v6 from 80+ files to ~15 core files.
**Basis:** `direct:` `orchestrator.py` has 9 methods marked `# pragma: no cover`; `deadcode-baseline.py` has 115+ entries. 5-step playbook documented in `docs/solutions/`. DAG engine already canonical.
**Rationale:** Every deleted path is one fewer surface for PCL-wiring class of bugs. Shrinking Router v6 scopes the Rust port.
**Downsides:** Router v6 consolidation risks breaking one-off scripts; needs import-graph verification first.
**Confidence:** 90% | **Complexity:** Medium | **Status:** Unexplored

### 4. Hypothesis Property-Test Suite for PCL Constraint Invariants
**Axis:** Testing, formal verification & invariant chains
**Description:** Build Hypothesis property tests using 4-layer architecture: shared strategies, monotonic invariant theorems (loss >= 0, zero iff satisfied, monotonic tightening), DAG-level output contract type validation against manifest declarations. CI gate.
**Basis:** `direct:` Hypothesis 4-layer architecture proven in Router V6. `direct:` `dag_engine.py:165` stores outputs without type validation. `reasoned:` PCL silent-skip would fail a `constraint_count > 0` property test.
**Rationale:** Property tests compound — written once, run forever. Every future loss bridge change gets automatic regression coverage.
**Downsides:** JAX non-determinism may cause flaky tests; need tolerance thresholds. Competing constraints may violate monotonicity.
**Confidence:** 80% | **Complexity:** Medium | **Status:** Unexplored

### 5. Z3 SMT Pre-Placement Satisfiability Gate
**Axis:** Testing, formal verification & invariant chains
**Description:** Before JAX placement, encode PCL geometric constraints as Z3 SMT formulas. Prove satisfiability. `unsat` = contradictory constraints caught at manifest-edit time. Vacuous constraints (empty PCL) trigger warning. Also serves as post-hoc verification.
**Basis:** `external:` Z3 SMT solvers standard for geometric constraint verification in analog placement. `reasoned:` Unsatisfiable constraint set would thrash optimizer indefinitely — Z3 catches in seconds.
**Rationale:** Definitive yes/no verification with exact arithmetic. Safety-critical for induction cooker hardware.
**Downsides:** Board geometry x component count may exceed Z3 limits for nonlinear constraints; keepout rectangles best initial target.
**Confidence:** 75% | **Complexity:** Medium-High | **Status:** Unexplored

### 6. MADR ADR for Constraint System Migration + Pipeline Governance
**Axis:** Documentation, ADRs & Rust migration
**Description:** MADR-format ADR documenting dual-constraint situation, silent-skip bug, migration path, sunset gates. CI gate requiring ADR for any DAG topology change (add/remove/rename/reorder stage). Bidirectional traceability matrix (ADR <-> code via @req annotations).
**Basis:** `direct:` Two constraint systems coexist with no documented decision about canonical. `external:` MADR specification industry-standard. `direct:` `@req` annotations and `TRACEABILITY.md` already exist.
**Rationale:** Dual-constraint bug exists because `optimize` forked from `input_stage` without documented decision. ADR prevents re-litigation.
**Downsides:** ADR overhead on small topology changes; consider size threshold for rename-only.
**Confidence:** 85% | **Complexity:** Low | **Status:** Unexplored

### 7. Profiling-Guided Rust Extraction — Constraint Engine First
**Axis:** Documentation, ADRs & Rust migration
**Description:** Profile pipeline with Survivor #2's middleware. Extract PCL constraint engine (752+481 lines) to Rust via PyO3+maturin — it's correctness-critical, self-contained, consumed by both CLI and DAG. Follow with A* priority queue kernel from Router v6. Station-by-station (brigade kitchen) extraction behind same StageHandler interface.
**Basis:** `external:` PyO3+maturin industry standard (Polars, Pydantic-core). `nalgebra` for geometry, `Rayon` for parallelism. `reasoned:` PCL ideal first target: small, self-contained, correctness-critical. Rust's type system eliminates missing-constraint-handler bugs.
**Rationale:** Big-bang Rust rewrite blocks all other work. Station-by-station keeps migration as background activity. Toolchain investment amortized over N extractions.
**Downsides:** Mixed Python/Rust build complexity; PyO3 crossing overhead vs JAX loop context must be benchmarked.
**Confidence:** 75% | **Complexity:** High | **Status:** Unexplored

## Rejection Summary

| # | Idea | Reason |
|---|------|--------|
| - | Hard-Fail toggle / Fail-Loud PCL / Auto-Enrich Delegate / Load-Time Enrichment / PCL as Rendering Backend | Merged into Survivor #1 — implementation strategies for PCL unification |
| - | VVQ Cascade / Double-Entry Reconciliation | Governance metaphors; Survivor #4's property tests + #6's ADR provide equivalent safety more pragmatically |
| - | Structured Logging / Per-Stage JAX Profiling / Stage-as-Metric-Emitter / Canary Metrics / Universal Telemetry / Pilot's Logbook / SPC Andon Cord / CI-Enforced Budget | Merged into Survivor #2 — components of DAG-native observability middleware |
| - | Kill Legacy Monolith / Silent Skip = Delete Permission / Dead Code SLA / Superseded-By Annotations / Router v6 Consolidation as standalone | Merged into Survivor #3 — dead-code playbook coverage |
| - | Hypothesis Auto-Generation / Contract Oracles as DAG Stages / No-Trust Boundaries / Load-Path Certificates | Merged into Survivor #4 — property-test + invariant chain |
| - | SMT Verification / Pre-Placement Z3 Gate / Z3 Verification Layer | Merged into Survivor #5 |
| - | ADR-Driven Rust Strategy / ADR-First Governance / Mise en Place Migration / Backward Rust Migration / Strangler Fig A* Extraction / Rust Extraction by Stage / Contract Traceability Matrix | Merged into Survivor #6 or #7 |
