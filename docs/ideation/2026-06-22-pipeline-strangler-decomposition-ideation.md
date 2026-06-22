---
date: 2026-06-22
topic: pipeline-strangler-decomposition
focus: Breaking down the main pipeline into smaller, testable, verifiable pieces using the strangler pattern
mode: repo-grounded
---

# Ideation: Temper Pipeline Strangler Decomposition

## Grounding Context

### Codebase Context

Temper has three overlapping PCB design automation pipeline systems:

1. **PipelineOrchestrator** — 8-phase monolith: INPUT→SEMANTIC→TOPOLOGICAL→PREFLIGHT→GEOMETRIC→ROUTING→REFINEMENT→OUTPUT. Phase handlers are 60-100 line methods in one class. `_run_geometric` hardcodes 500 epochs. `_run_refinement` constructs MazeRouter inline. No DI. No mocks.

2. **RouterV6Pipeline** — 5-stage: Stage0(parse)→Stage1(escape vias)→Stage2(channel analysis, 8 sub-steps monolith)→Stage3(SAT, 5s timeout)→Stage4(A* geometric, smoothing, via placement all in one method). Well-typed StageOutput dataclasses. Completion rate: **0.5%**.

3. **DeterministicPipeline** — 26 Stage subclasses with immutable BoardState (frozen dataclass). run(state)→new state. Cleanest architecture.

Key pain: Two pipeline systems not composed. Coverage gate only on core/ (25 modules), router_v6/ (52 modules) uncovered. 118 ad-hoc scripts. Confusing temper-placer/ vs packages/temper-placer/ dual layout.

### Past Learnings

1. **Pipeline Refactoring Plan** (Jan 2026) — 11 fragmented state classes, 9+ router APIs, 48 scripts. Proposes Router Protocol + Strategy pattern.
2. **Active Pipeline Gap plan** (June 2026) — Strangler fig IN PROGRESS. Adapter modules wrap existing components. `benders_placement()` wraps `place_power_stage_template`, `route_pcb()` wraps `RouterV6Pipeline.run()`. Closure test is integration gate.
3. **RouterV6 immutable BoardState** with phantom types for stage ordering.
4. **PowerPlaneStage** hardcoded net list silently overwrote LayerAssignmentStage decisions — derive from net_class, use immutable types.
5. **TDD per-concern** — 5 test files each targeting one isolation concern. 96.7% clearance pass rate achieved.
6. **Waterfall pipeline failure** — placed unroutably, added Routability Validation Loop with feedback.
7. **Router V6 Quality Plan** — 7 fixes for 0.5%→>10% completion. Closure test as gate.

### External Context

- **FreeRouting** — Monolithic→modular decomposition with ArchUnit-enforced boundaries. 5-stage DSN→SES pipeline.
- **Fowler Strangler Fig (2024)** — identify seams→build façade→parity-test→replace incrementally. Transitional architecture is necessary, not waste.
- **Commercial EDA** — All separate strategy/execution/verification into independently upgradable components.
- **Compiler pipeline** — Multiple IRs, pass managers, regression suites. Pass: read IR→transform→validate→revert on failure.
- **DSN/SES format** — Industry-standard intermediate format. Human-readable, diffable. Natural seam for pipeline decomposition.
- **Property-based testing** — Geometric invariants (connectivity, clearance, non-overlap), oracle testing, constrained generation.

## Topic Axes

1. **Pipeline boundary design** — Data contracts and intermediate formats between stages
2. **Stage extraction and isolation** — Which monoliths to split first into testable sub-stages
3. **Testing infrastructure** — Harnesses, golden fixtures, PBT, coverage gates per-stage
4. **Integration and orchestration** — Unifying three pipeline systems under common interface
5. **Verification gates** — DRC/connectivity/invariant checks as strangler safety nets

## Ranked Ideas

### 1. DSN/SES Universal Seam — Standardize Stage Boundaries First
**Axis:** Pipeline boundary design
**Basis:** `external:` FreeRouting's 5-stage DSN→SES modular decomposition with ArchUnit-enforced boundaries proves this pattern. DSN/SES is the de facto industry standard for EDA-to-autorouter interchange, supported by KiCad, EAGLE, Altium, and FreeRouting. `direct:` The existing closure test adapters (benders_placement, route_pcb) already serialize to temp `.kicad_pcb` files as a workaround — DSN/SES formalizes this ad-hoc pattern into a first-class contract.
**Rationale:** Without a common intermediate format, the strangler fig's parity tests are impossible — old and new paths speak different languages. DSN is the Rosetta Stone. Standardizing first means every subsequent refactor inherits a common interface for free.
**Downsides:** DSN may not capture all KiCad-specific data (zone fills, custom pad shapes). Requires DSN export/import plumbing for every stage.
**Confidence:** 92%
**Complexity:** Medium
**Status:** Explored

### 2. Golden Fixture Ladder — Per-Seam Parity Testing as Strangler Safety Net
**Axis:** Testing infrastructure
**Basis:** `external:` Fowler's strangler fig pattern explicitly requires "build façade → parity-test → replace incrementally" at each identified seam. `direct:` The closure test already serves as the integration gate — golden fixtures extend this to per-seam verification. The TDD per-concern success (96.7% clearance pass rate from 5 targeted test files) proves targeted testing catches pin-hole issues.
**Rationale:** Without per-seam parity testing, every extraction is a gamble. Golden fixtures make extraction self-certifying — if the new stage's DSN output matches the old's golden, it's safe to deploy. The ladder grows as new test boards are added.
**Downsides:** Initial golden fixture generation requires running the full monolith on canonical boards. Diff semantics for geometric data may require tolerance thresholds (small coordinate shifts ≠ regression).
**Confidence:** 88%
**Complexity:** Medium
**Status:** Explored

### 3. Unified Stage Protocol — One Interface Across All Three Pipeline Systems
**Axis:** Integration and orchestration
**Basis:** `direct:` DeterministicPipeline already uses 26 Stage subclasses with immutable BoardState and `run(state) -> new state` — the cleanest architecture in the codebase. The Pipeline Gap plan wraps `benders_placement()` and `route_pcb()` in adapters — these are proto-protocols. `external:` Fowler's strangler fig prescribes façades with identical input/output contracts for old and new implementations.
**Rationale:** A unified protocol means RouterV6's SAT solver can hand off to DeterministicPipeline's clearance validation without either system knowing about the other. New pipeline implementations plug in without touching client code. Evolutionary improvement via closure test.
**Downsides:** Protocol design is political (what goes in StageInput/Output?). Strategy dispatch with one implementation is premature abstraction — risk of dead weight if only one pipeline survives.
**Confidence:** 78%
**Complexity:** Medium
**Status:** Explored

### 4. Orchestrator → Declarative Stage DAG + First-Class Feedback Contracts
**Axis:** Integration and orchestration
**Basis:** `direct:` PipelineOrchestrator has 8 phases in one class with 60-100 line handler methods. `_run_geometric` hardcodes 500 epochs; `_run_refinement` constructs MazeRouter inline. The waterfall pipeline placed unroutably and required an ad-hoc Routability Validation Loop. `external:` Compiler pass managers use dependency-declared passes with fixed-point iteration.
**Rationale:** The orchestrator is the single biggest blocker to testability. Removing it forces every phase to be independently instantiable, configurable, and testable. Feedback contracts turn placement↔routing loops from code into configuration.
**Downsides:** Some phase interdependencies may not be cleanly expressible as DAG edges. DAG executor adds indirection; orchestration bugs become framework bugs.
**Confidence:** 75%
**Complexity:** High
**Status:** Explored

### 5. Decompose RouterV6 Stage 2 Channel Analysis into Verifiable Micro-Stages
**Axis:** Stage extraction and isolation
**Basis:** `direct:` RouterV6Pipeline `_run_stage2` in `router_v6/pipeline.py:241-326` is 85 lines of sequential sub-step calls with well-typed intermediate dataclasses — each sub-step is already logically separated. Completion rate is 0.5%; channel analysis is the input to both SAT and A*. `reasoned:` Each sub-step extracted removes one variable from "why does routing fail?" debugging space.
**Rationale:** Decomposing Stage 2 turns the 0.5% completion rate from a black box into independently debuggable sub-steps. As each sub-step is hardened with property-based tests, the completion rate should ratchet upward monotonically.
**Downsides:** Sub-steps have hidden interdependencies — occupancy grid computation depends on channel widths which depend on skeletons. The first extraction is the hardest.
**Confidence:** 90%
**Complexity:** Medium
**Status:** Explored

### 6. Per-Stage DRC Fence — Verification Gates as Strangler Safety Net
**Axis:** Verification gates
**Basis:** `direct:` TDD per-concern achieved 96.7% clearance pass rate using targeted invariant checks. PowerPlaneStage silently overwrote LayerAssignmentStage because no per-stage gate existed. Waterfall pipeline failure was caught only after routing failed — a placement DRC fence would have caught unroutable placements earlier. 8 parallel sub-agents independently converged on this concept. `external:` Compiler pipelines run verification passes between optimization passes; commercial EDA runs DRC incrementally.
**Rationale:** The current pipeline is a black box where failures discovered at the end require tracing backward through 8 phases. Dual-run invariants make strangler replacement self-certifying.
**Downsides:** Running DRC at every stage adds compute overhead. Some invariants require global board context. Wrong invariants create false positives.
**Confidence:** 85%
**Complexity:** Medium
**Status:** Unexplored

### 7. Import-Linter Module Boundary Enforcement — Prevent Structural Regression
**Axis:** Verification gates
**Basis:** `external:` FreeRouting used ArchUnit to enforce modular boundaries during its monolithic-to-modular decomposition — the exact same constraint class. `direct:` The coverage gate (on core/ only) is the only existing CI enforcement — nothing prevents new code from importing monolith internals. 118 scripts import from all over the codebase with no restriction.
**Rationale:** Coverage gates say "is this code tested?" Import-linter gates say "is this code in the right module?" Both are strangler safety nets, but import-linter prevents the strangler from becoming a kudzu vine — new modules accidentally depending on old internals.
**Downsides:** Initial boundary definition requires consensus on what constitutes "core" vs "heuristics" vs "pipeline." False positives during CI can block legitimate refactors.
**Confidence:** 82%
**Complexity:** Low
**Status:** Explored

## Rejection Summary

| # | Idea | Reason |
|---|------|--------|
| C4 | Decompose Stage 3 SAT Solver | Duplicates #5 — Stage 2 has higher ROI as first extraction target |
| C5 | Invert Routing: CSP + Composable Solvers | Aspirational CSP rewrite — better handled as a brainstorm variant |
| C7 | Per-Net Routing as Functional Fold | Narrower pattern within broader RouterV6 decomposition |
| C8 | Extract Geometry Engine | Sub-step of orchestrator DAG decomposition (#4) |
| C9 | Stage Prioritization via Blame Assignment | Valuable measurement tool but not structural — pre-extraction diagnostics |
| C10 | Router-as-Predictor: ML-Inferred Stage | Too expensive at 0.5% completion baseline; fix heuristics first |
| C12 | Coverage Gate Expansion + PBT | Operational follow-on — golden fixtures (#2) and DRC fence (#6) are more strategic |
| C13 | DRC Profile Fingerprinting | Folded into #6 as a sub-feature of per-stage DRC fence |
| C14 | Million-Design Regression Corpus | Too expensive as first move — start with golden fixtures (#2) |
| C15 | Differential Oracle Across Variants | Covered by golden fixture parity testing (#2) |
| C18 | Collapse Dual Package Layout | Housekeeping, not strategic decomposition |
| C19 | Ticket/Plate Station Autonomy | Duplicates #3+#4 — protocol and DAG capture the same pattern |
| C20 | Incremental Recompute: Cache-Keyed Pipeline | Optimization, not structural decomposition |
| C21 | Wetland Bypass Pattern | Folded into #4's stage skip mechanism within DAG executor |
| C24 | DRC-as-a-Service Façade | Duplicates #6 — per-stage DRC fence achieves same goal |
| C25 | Universal Test Harness (synthesis) | Captured by #1+#2 |
| C26 | Safe Extraction Framework (synthesis) | Captured by #3+#7 |
| C27 | Adversarial Verification (synthesis) | Captured by #6 |
