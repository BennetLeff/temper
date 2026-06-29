---
date: 2026-06-29
topic: root-cause-breadcrumb-trail
origin: docs/plans/2026-06-28-011-feat-pipeline-observability-plan.md
status: brainstorm-phase-2
---

# Brainstorm: Root-Cause Breadcrumb Trail

## Problem Statement

**Who:** Pipeline operators and maintainers who encounter a stage failure (DRC violation, routing failure, placement breach) in a multi-stage EDA pipeline.

**What problem:** When a pipeline stage fails, the operator sees only the terminal symptom — e.g. "DRC failed: Plane 3 overlaps pad U2-14." The actual root cause may have been introduced 2-3 stages earlier (e.g. placement at iteration 47 pushed U2 into a congested area that made it impossible for the plane generator to route clearance). Today's system captures per-stage events (`PipelineExecutionLog.events`, `StageDRCFailure.stage`) but has **no causal links between stages** — there is no mechanism to answer "what upstream decision caused this downstream failure?"

**What changes:** A backward-causal trace that links each failure artifact to its upstream provenance. When DRC fails on Plane 3 overlapping U2-14, the breadcrumb trail surfaces: `DRC(failure) → PlaneGeneration(U2 clearance=0.1mm below min 0.5mm) → Placement(iteration=47, U2 at (12.7, 3.4), pushed by netlist_pitch_constraint)`.

This transforms the operator's experience from "the pipeline is red" into "the pipeline is red because U2 was placed too close to the board edge at iteration 47 due to netlist pitch constraint."

## Existing Context (Verified from Codebase)

### Data Flow Between Stages

Pipeline stages exchange data via a YAML-defined DAG manifest at `packages/temper-placer/configs/pipeline_default.yaml`. The `StageDAGEngine` (`dag_engine.py:34`) manages topology via `provides`/`requires` keys on each `StageDefinition`:

```
input → [board, netlist, constraints, loops]
semantic → [loops_enriched]
topological → [deterministic_result]
geometric → [placement_state]
routing → [routing_result, routing_completion]
refinement → [refinement_placement, refinement_routing_result]
output → [output_files, physics_report]
```

Data exchange occurs through a shared runtime `dict[str, Any]` context (`dag_engine.py:128-276`). After each stage executes, `result.outputs` (a `dict[str, Any]` from `StageResult`) is merged into the context (`dag_engine.py:207-208`) — upstream outputs become downstream inputs implicitly. **There is no metadata tagging** that records which context key was produced by which stage, at what iteration, or with what provenance.

### PipelineExecutionLog — Existing Instrumentation

`PipelineExecutionLog` (`dag_observability.py:40-59`) captures:
- `dag_topology`: requires/provides per stage
- `stage_order`: execution order
- `stage_timings`: per-stage wall clock
- `retry_counts`: retries per stage
- `feedback_activations`: contract name, from→to stage, attempt count, parameter adjustments
- `success` / `total_duration_s`
- `events`: list of `StageEvent` (name, kind, iteration, duration_s, outputs dict)

Currently, `PipelineExecutionLog.to_dict()` **excludes the `events` list** (`dag_observability.py:50-59`) — the serialized JSON at `pipeline_execution.json` does not contain per-stage event data. Plan 011 R2 explicitly extends this.

`PipelineExecutionLog` does **not** carry upstream references. Events are linear log entries with no "caused by" or "derived from" links. The feedback activation records (`feedback_activations`) capture retrigger data but only at the contract level (which contract fired, from/to stage), not at the artifact level.

### DRC Fence — Stage Attribution

The DRC fence operates at two levels:

1. **Per-stage validators** (`router_v6/stage_validators.py:22-29`): `StageDRCFailure` carries `field`, `value`, `reason`, and `stage` (stage name). Registered validators run on `BoardState` after each router sub-stage. The `run_validators()` function (`stage_validators.py:46-55`) discovers and executes validators but **does not capture upstream context** — the failure message is self-contained.

2. **Placement-level DRC fence** (`deterministic/stages/phased_component_assignment_validator.py`): Per-stage DRC fence for `PhasedComponentAssignmentStage`. Returns `StageDRCFailure` entries with stage attribution but no provenance chain.

### StageLedger — Object Cardinality Tracking

`StageLedger` (`router_v6/stage_ledger.py:54-124`) tracks object counts (nets, components, channels, vias, segments) across stage boundaries. It detects imbalances (`StageLedgerImbalanceError`) but **does not record artifact-level provenance or causal chains**. It validates that "what went in matches what came out" but does not link outputs to their generating inputs.

### Profiling — No Causal Data

`PipelineProfiler` (`profiling/instrumentation.py:105`) records `StageTiming` (wall_time, cpu_time, sub_steps) via context-manager instrumentation. It measures performance but carries **no causal or provenance metadata**.

### Explainability — Decision Tracing (Seeded but Unwired)

`DecisionLogger` (`pipeline/explainability.py:12-66`) logs placement and routing decisions with reasons and constraint references into a `DecisionTrace`. This is the closest existing mechanism to provenancer — it records *why* a decision was made. However:
- It is **not wired** into the DAG engine or any stage handler
- It only covers placement/routing decisions, not geometric artifacts
- It has no backward-linking from failures to decisions

### BottleneckReport — Forward-Flowing Feedback

`BottleneckReport` (`pipeline/bottleneck_report.py:100-167`) captures routing failures with per-net spatial data, congestion heatmaps, and bottleneck regions. It is consumed by the placer's feedback loop. This is **forward-flowing** feedback (router → placer) but could serve as a breadcrumb link point: when DRC fails, the bottleneck report could explain *why* routing failed, which in turn traces back to placement.

### Summary of Gaps

| What Exists | What's Missing |
|---|---|
| `StageDAGEngine` tracks `provides`/`requires` statically | No runtime artifact-provenance mapping |
| `PipelineExecutionLog.events` captures per-stage outputs | No causal links between events |
| `StageDRCFailure` has `stage` field | No upstream-stage reference chain |
| `StageLedger` tracks cardinality | No artifact-identity provenance |
| `DecisionLogger` records "why" per decision | Not wired to failure artifacts |
| `FeedbackContract` captures stage→stage retrigger | No artifact-level cause→effect |
| `BottleneckReport` describes routing failures spatially | No backward-trace to placement decisions |
| `context` dict merges stage outputs | No metadata on which stage produced which value |

## Users & Use Cases

- **U1. Pipeline operator debugging a CI failure:** Terminal shows "DRC failed." Runs `/breadcrumb drc` to see the three-level trace: (1) DRC failure → (2) Plane 3 overlap at U2-14 → (3) Placement iteration 47, U2 at (12.7, 3.4), netlist pitch constraint 5.0mm. Saves 30+ minutes of manual reproduction.

- **U2. Pipeline maintainer investigating a regression:** A previously-passing board now fails DRC. Uses breadcrumbs to identify *which* upstream decision changed — discovers that the NSGA-II seed changed iteration 47's component ordering, causing a previously-safe placement to violate clearance.

- **U3. PR author assessing placement code change impact:** Makes a change to the loss function. Receives PR comment showing not just "routing completion dropped 3%" but "3 nets became unroutable because placement pushed components Q3, Q4 into the bottleneck region at (45.2, 67.8)."

- **U4. Tool builder validating a new stage:** Adds a new "thermal-aware" placement stage. Uses breadcrumbs to verify that downstream routing failures are *not* caused by the new stage — the breadcrumb shows the failure traces back to a netlist constraint, not thermal re-routing.

## Success Criteria

1. **S1.** A DRC failure can be traced backward to its originating placement decision (component + iteration + constraint reason) within 5 seconds of querying, without re-running the pipeline.

2. **S2.** The breadcrumb trail survives pipeline artifact serialization (JSON output) and can be consumed by downstream tooling (PR scorecard, HTML report, health-digest) without a re-evaluation pass.

3. **S3.** The causal link carries enough context (position, iteration, constraint name) that a maintainer can reproduce the upstream state in a debug scenario without additional instrumentation.

4. **S4.** The instrumentation overhead for breadcrumb collection is <5% of total pipeline wall-clock time across all stages.

5. **S5.** Breadcrumb data is self-validating — a cross-check against the DAG topology (requires/provides graph) confirms that claimed upstream links follow valid data-flow edges.

## Approach 1: Artifact-Provenance Tagging in Context

**Description:** When `StageDAGEngine` merges `result.outputs` into the runtime `context` dict (`dag_engine.py:207-208`), each context key is tagged with a provenance record: `{producing_stage, iteration, key, dependency_keys_used}`. The context becomes a provenance-aware data structure rather than a bare dict. When a downstream failure occurs (DRC, routing error), the failing stage's handler records which context keys it consumed and the provenance tag chains back.

At serialization time (`write_execution_log_json`), the provenance graph is written as `provenance_edges` in `PipelineExecutionLog` — a list of `(source_stage, output_key, consumer_stage, input_key)` edges.

**Pros:**
- Minimal intrusion: modifies `context` merging, not individual stage handlers
- Transparent to existing observers — `StageEvent.outputs` already captures output dict
- Can be implemented in `dag_engine.py` alone (no per-stage changes needed)
- Natural fit with `PipelineExecutionLog` serialization (add one field)

**Cons / Risks:**
- Distinguishes "used" from "present in context" — a stage may have access to a key but not consume it. Requires stage handlers to declare which keys they actually read (currently they `context["board"]` implicitly).
- Feedback retriggers clear context keys (`dag_engine.py:223`) — provenance must be cleared or invalidated on retrigger.
- Context is a flat dict; deeply nested objects (e.g., `placement_state.positions` is a JAX array) lose provenance at the field level unless additional nesting is introduced.
- Must re-serialize provenance edges on every run, adding overhead.

**Key unknowns:**
- How to handle partial consumption (stage reads `placement_state` but only uses `positions`, not `rotations`)?
- Provenance invalidation on feedback retrigger — should cleared context keys be marked as "regenerated"?

**Best suited when:** Stages already declare their actual data dependencies (not just what's available in context). The DAG manifest `requires` list is a good starting point but may over-declare.

---

## Approach 2: Post-Hoc Reconstruction from DAG Topology + PipelineExecutionLog

**Description:** Instead of instrumenting the runtime for provenance, reconstruct the causal chain post-hoc using three existing data sources: (1) the DAG manifest's `provides`/`requires` graph (static data-flow edges), (2) `PipelineExecutionLog.events` (per-stage timestamps and outputs), and (3) `StageDRCFailure` entries (failure attribution). A query-time function walks backward from a failure through the known dependency graph to find the upstream stage that produced the offending artifact.

The reconstruction works by joining `failure.stage` → manifest `requires` list → `provides_map` → upstream stage, then examining that stage's `StageEvent.outputs` to extract the specific artifact. This is a read-only query over already-serialized data — no runtime instrumentation.

**Pros:**
- Zero runtime overhead — no per-stage changes, no context modifications
- Works retroactively on existing `pipeline_execution.json` artifacts (once `events` is included in serialization)
- No feedback/retrigger invalidation problem — reconstruction is based on the final execution state
- Simple implementation: a `breadcrumb.py` script that reads DAG manifest + pipeline_execution.json + failure data

**Cons / Risks:**
- Cannot distinguish "which" parameter within an upstream artifact caused the problem (e.g., `placement_state` is one blob, not component-level provenance)
- If a stage consumes multiple upstream artifacts, the reconstruction can only narrow to "it came from stage X" but not "which field of stage X's output"
- Feedback retriggers mean the same stage may have run multiple times — the `PipelineExecutionLog` has all events but the final `events` list must distinguish the "winning" execution
- Requires `PipelineExecutionLog.to_dict()` to include `events` (Plan 011 R2 addresses this)

**Key unknowns:**
- Is the `StageEvent.outputs` dict detailed enough to provide useful attribution (component name, position, iteration) or is it a coarse blob (e.g., just `placement_state: PlacementState@0x7f...`)?
- What level of granularity do operators actually need — stage-level or component-level?

**Best suited when:** Quick v1 delivery is prioritized. The DAG topology + execution log already contain the backbone; query-time enrichment adds value without touching the runtime path.

---

## Approach 3: Hierarchical Annotation Token (Inversion — Push-Backward from Failure Detectors)

**Description:** Instead of modifying the forward pipeline to carry provenance, make the *failure detectors* (DRC fence validators, routing error handlers, convergence checkers) responsible for reaching backward and annotating failures with upstream context. Each `StageDRCFailure` gains an optional `upstream_ref` field. When a validator detects a failure, it has full access to `BoardState` (which carries `placement_state`, `constraints`, `design_rules`, etc.) and can introspect up the pipeline.

For example, `validate_phased_component_assignment_hv` already examines placement positions, netlist pins, and creepage rules. If a DRC failure occurs, the validator could record: `upstream_ref={"stage": "geometric", "iteration": 47, "component": "U2", "position": (12.7, 3.4), "constraint": "pitch_constraint_5mm"}`. This is the existing data — the validator already computes it; it just doesn't attach it to the failure.

**Pros:**
- No modification to the forward pipeline flow or context dict
- Each failure detector knows *exactly* what upstream data caused the violation (it computed the check from that data)
- `StageDRCFailure` already has extensible fields — adding `upstream_ref` is a non-breaking schema change
- High precision: the failure message says "slot (12, 8) unblocked for U2.pin3 at (12.7, 3.4)" — the upstream ref just caches what the validator already computed

**Cons / Risks:**
- Places the burden on each validator author — adoption is uneven unless enforced by convention or linting
- Only covers DRC-style failures, not routing failures or convergence failures (which have different data structures)
- Upstream ref is "best effort" — a validator cannot trace further than its own data access (e.g., it sees placement but doesn't know *why* placement chose that position)
- Requires updates to all existing validators (20+ registered validators across router sub-stages)

**Key unknowns:**
- Can routing failure data structures (`BottleneckNetEntry`, congestion heatmaps) carry equivalent upstream refs?
- What format should `upstream_ref` take to be consistently queryable?

**Best suited when:** High-precision, high-detail failure tracing is the priority. The failure detectors already hold the data — this approach makes them responsible for surfacing it.

---

## Approach 4: Hybrid — Context Annotations + Failure-Boundary Enrichment (Recommended)

**Description:** Combine the lightness of Approach 2 (post-hoc reconstruction) with the precision of Approach 3 (failure-detector annotations) and the infrastructure of Approach 1 (provenance metadata on context keys). The three layers work together:

1. **Layer 1 — Context provenance (lightweight):** At each stage boundary, `StageDAGEngine` records a minimal provenance edge: `(stage, iteration) → {key: (producer_stage, producer_iteration)}`. This is computed at merge time (`dag_engine.py:207-208`) and costs O(outputs). Stored in `PipelineExecutionLog.provenance_edges`.

2. **Layer 2 — Post-hoc DAG reconstruction:** A `breadcrumb.py` query tool reads `pipeline_execution.json` (with `provenance_edges` + `events`) and walks the DAG topology to reconstruct the full backward chain from any failure artifact. This handles stage-to-stage attribution.

3. **Layer 3 — Failure-enriched upstream refs (opt-in, per-stage):** DRC fence validators and routing failure handlers optionally include an `upstream_ref` dict on `StageDRCFailure`s with sub-component detail (component ref, position, constraint name). This is additive — Layer 2 provides the backbone; Layer 3 provides precision where it's cheap to add.

**Output:** A three-level breadcrumb trail matching Plan 011's three-level hierarchy:

```
Level 1 (Overview):  "DRC failed on PhasedComponentAssignment."
Level 2 (Stage detail): "Plane 3 overlapping pad U2-14 — clearance 0.1mm < min 0.5mm."
Level 3 (Root cause): "Placement iteration 47 placed U2 at (12.7, 3.4).
                        Constraint: netlist_pitch_constraint=5.0mm pushed U2
                        into bottleneck region."
```

**Pros:**
- Layer 1 (context provenance) is implemented once in `dag_engine.py` and covers all stages automatically
- Layer 2 (post-hoc reconstruction) works for any failure, even from stages without Layer 3 annotations
- Layer 3 (failure-enriched refs) provides high precision where needed, with no forcing function
- All data lives in existing serialization paths (`pipeline_execution.json`, `StageDRCFailure`)
- Can be consumed by Plan 011's HTML report (adds a "Root Cause" section) and PR scorecard

**Cons / Risks:**
- Three-layer design adds complexity in query logic — the `breadcrumb.py` tool must merge all three sources
- Context provenance must survive feedback retriggers (context clearing on retrigger needs synchronized invalidation)
- Layer 3 adoption is uneven — there must be a convention or CI check to prevent bitrot

**Key unknowns:**
- Whether `StageEvent.outputs` dicts are detailed enough for Layer 2 reconstruction (current outputs are dicts with values like `PlacementState` objects — serialization detail matters)
- Optimal format for `upstream_ref` on `StageDRCFailure` — should it be a free-form dict or a constrained schema?

**Best suited when:** Delivering the full three-level hierarchy from Plan 011 with progressive depth — Layer 1+2 ship in v1, Layer 3 annotations accumulate over time.

---

## Recommendation

**Approach 4 (Hybrid — Context Annotations + Failure-Boundary Enrichment)** is recommended because:

1. It directly realizes Plan 011's three-level hierarchy (overview → stage detail → root cause) with a layered, incrementally deepenable design.
2. Layer 1+2 (context provenance + post-hoc reconstruction) can ship in a single implementation unit with changes confined to `dag_engine.py`, `dag_observability.py`, and a new `breadcrumb.py` query tool — all in the pipeline package.
3. Layer 3 (failure-enriched `upstream_ref`) leverages existing `StageDRCFailure` structure and per-validator data access — validators that already compute cause data can start annotating immediately.
4. The entire trail is serializable via the existing `pipeline_execution.json` path (extended with `provenance_edges`), making it consumable by Plan 011's HTML report, PR scorecard, and health-digest without new artifact formats.

This directly answers the problem: "the pipeline is red because U2 was placed at (12.7, 3.4) at iteration 47 due to netlist pitch constraint."

## Scope Boundaries

### In scope for v1

- U1: `provenance_edges` field on `PipelineExecutionLog` — recorded at context-merge time in `StageDAGEngine` (`dag_engine.py:207-208`)
- U1: Extend `PipelineExecutionLog.to_dict()` to include both `events` and `provenance_edges` (extends Plan 011 R2)
- U2: `scripts/breadcrumb.py` query tool — backward trace from failure to root cause using DAG topology + provenance_edges + events
- U2: Three-level output format: overview summary, per-stage detail, root cause with component/constraint attribution
- U3: Wire Layer 3 `upstream_ref` on `StageDRCFailure` for `PhasedComponentAssignmentStage` validator (highest-value DRC fence point)
- U4: Integration test: known-bad placement + routing → DRC failure → breadcrumb trace verifies correct attribution

### Deferred for later

- Full Layer 3 annotation across all 20+ router sub-stage validators — ship the pattern on one validator, adopt progressively
- Breadcrumb integration into PR scorecard (Plan 011 U8) — v1 breadcrumbs are a standalone query tool
- Breadcrumb integration into HTML report (Plan 011 U7) — adds a "Root Cause" section to `pipeline_report.py`
- Field-level provenance (e.g., `placement_state.positions[U2]` not just `placement_state: produced by geometric`)

### Outside this feature's identity

- Live debugging session with interactive breadcrumb exploration — this is a CI artifact query tool, not a WebSocket-served debugging SPA
- Automatic fix suggestion from breadcrumbs — covered by existing `analyze_root_cause()` in `feedback.py`
- Forward predictive "what-if" from breadcrumb data — covered by convergence copilot brainstorm (deferred)
- Trace-to-decision mapping (explainability integration) — DecisionLogger is not wired and would be a separate integration
