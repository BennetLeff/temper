---
title: "feat: Deploy Strangler to RouterV6 Stage 3 (SAT Solver) into 5 Micro-Stages"
type: feat
status: active
date: 2026-06-22
origin: docs/ideation/2026-06-22-test-and-build-next-ideation.md
---

# feat: Deploy Strangler to RouterV6 Stage 3 (SAT Solver)

## Summary

Extract `RouterV6Pipeline._run_stage3` (`router_v6/pipeline.py:388-442`), a monolithic call chain of 5 sequential sub-steps (constraint generation, variable mapping, SAT solve, assignment validation, model extraction), into 5 independent `Stage` subclasses conforming to the DeterministicPipeline's `Stage(ABC)` protocol (`run(state: BoardState) -> BoardState`). A `Stage3Orchestrator` chains the micro-stages in dependency order and a backward-compatibility adapter assembles `Stage3Output` from the final `BoardState` so `_run_stage4` operates unchanged. Each micro-stage is backed by golden fixture parity tests on 4 canonical boards, property-based tests (hypothesis, >=100 examples), a per-stage DRC gate, and a >=90% per-module line-coverage gate. All infrastructure (protocol, golden format, CI gates, DRC fence) from the Stage 2 decomposition is already built and proven.

---

## Problem Frame

Router V6 Stage 3 (topological routing via SAT) feeds Stage 4 (A* geometric realization). If constraint generation produces an over-constrained model, variable mapping drops channels, the SAT solver timed out, or topology extraction misinterprets the assignment, Stage 4 silently receives a malformed `TopologyGraph` and fails without clear attribution. Each sub-step already has its own module (`constraint_model.py`, `sat_model.py`, `topology_solver.py`, `topology_extraction.py`) and low-level tests, but no per-sub-step integration tests, golden fixtures, incremental DRC gates, or parity assertions against the monolith.

The DeterministicPipeline already defines a clean Stage protocol. Stage 2 decomposition has proven the pattern: 8 micro-stages, 4 canonical boards, golden parity, PBT, DRC fence, coverage gates. Stage 3 is simpler (5 sub-steps vs Stage 2's 8) and directly downstream of already-decomposed Stage 2 — meaning all upstream BoardState fields are already populated before Stage 3 begins.

---

## Scope Boundaries

### In scope

- R1–R7: BoardState extension, 5 micro-stage classes, Stage3Orchestrator + adapter, golden fixtures, PBT suites, DRC gates, coverage gates per module, monolith parity tests, extraction order enforcement.
- 5 implementation units (one per sub-step), plus the Stage3Orchestrator and parity tests.
- Construction of the `generate_stage3_goldens.py` fixture-generation script and `test_stage3_golden_parity.py` / `test_stage3_monolith_parity.py` parity tests.
- A `StageDRCFailure` error type and 5 `_validate(state) -> list[StageDRCFailure]` standalone validator functions, auto-discovered via the existing `@register_validator(name)` decorator in `router_v6/stage_validators.py`.

### Deferred

- Extracting Stage 4 (A* router). Stage 4 continues to receive `Stage3Output` unchanged.
- Integrating a real SAT solver backend (Z3, MiniSat). The simplified solver in `topology_solver.py` remains the backend.
- Parameterizing the Stage DAG for runtime reordering. The 5 micro-stages are chained in a fixed order.
- Implementing constraint model improvements. The micro-stages delegate to existing module-level functions unchanged.
- Cross-stage DRC gates. DRC validates invariants within a single stage only.

### Out of scope

- Changing the Stage 4 interface. `_run_stage4` continues to consume `Stage3Output`.
- Performance optimization beyond the <5% overhead bound.
- Adding new constraint types or SAT clauses beyond what the monolith currently generates.

---

## Stage 3 Sub-Step DAG

The monolithic `_run_stage3` decomposes into 5 sequential sub-steps forming a linear DAG (no branching — simpler than Stage 2's DAG):

```
ConstraintGeneration ──> VariableMapping ──> SATSolve ──> AssignmentValidation ──> ModelExtraction
```

| Step | Pipeline Lines | Module | Description |
|------|---------------|--------|-------------|
| 3.1–3.6 | 391–402 | `constraint_model.py` | Build `ConstraintModel` from skeletons, nets, channel_widths, design_rules |
| 3.7a | 407–413 | `sat_model.py` | Map constraint-model variables to SAT variables (`populate_sat_from_constraints`) |
| 3.7b | 420–423 | `topology_solver.py` | Solve SAT model with 5s timeout (`solve_topology`) |
| — | — | `topology_solver.py` | Validate assignment against all clauses (`_check_assignment`) |
| 3.9 | 432–435 | `topology_extraction.py` | Extract `TopologyGraph` from SAT solution (`extract_topology_solution`) |

Note: `_check_assignment` is already part of the solver module and is called internally during SAT solve; it's extracted as a standalone validation sub-step to enable independent testing and a DRC fence between SAT solve and model extraction.

---

## Key Technical Decisions

**K1. BoardState extension via frozen dataclass field addition (not subclass).** `BoardState` (`deterministic/state.py:25-60`) is a frozen dataclass where all fields use `= None` or `= field(default_factory=...)`. Adding 5 new `Optional[...] = None` fields does not break existing consumers. This is the same pattern used by Stage 2 decomposition (lines 49-57 already have 8 channel-analysis fields).

**K2. Five direct Stage subclasses, no mixin.** Each micro-stage's `run()` shape is identical (read from BoardState, call existing function, write to BoardState). A mixin adds indirection with no deduplication benefit. Same decision as Stage 2 K2.

**K3. Extraction order: forward (constraint → solve → extract).** The DAG is strictly linear. Extracting data producers first means each extraction can be verified by running real upstream stages (not mocks) against monolith intermediate state. Same decision as Stage 2 K3.

**K4. Stage3Orchestrator chains micro-stages + backward-compat adapter.** `Stage3Orchestrator` runs the 5 micro-stages in dependency order, threading `BoardState` through. `_run_stage3` is refactored to instantiate the orchestrator, run it, then assemble `Stage3Output` from the final `BoardState`. Stage 4 accesses `stage3.topology_graph` (channel_mapping.py, line 479) and `stage3.solution.is_satisfiable` — both available from the adapter.

**K5. Golden fixture format: JSON with custom encoders.** Same format as Stage 2 golden fixtures. Custom JSON encoders handle NetworkX graphs via `node_link_data`, SAT model/variables via dict serialization. A `--regenerate` flag gates intentional algorithm changes. Same decision as Stage 2 K5.

**K6. Per-stage DRC validators: standalone functions with existing `@register_validator` decorator.** The `stage_validators.py` module and `VALIDATOR_REGISTRY` already exist from Stage 2 decomposition. New validators register under `"ConstraintGeneration"`, `"VariableMapping"`, `"SATSolve"`, `"AssignmentValidation"`, `"ModelExtraction"`.

**K7. Coverage gate: per-module `pytest-cov` with `--cov-fail-under=90`.** Measured independently per module. Same decision as Stage 2 K7.

**K8. Performance regression bound: <5% wall-clock overhead on canonical boards vs monolith.** The extraction adds one function call per micro-stage + one `dataclasses.replace` per stage. Stage 3 wall time (5s timeout, typically <1s for current boards) dominates overhead.

---

## Implementation Units

### U0. BoardState Extension for Stage 3

**What:** Add 5 Stage 3 topological-routing fields to `BoardState` (`deterministic/state.py`). Register 5 validator names in the existing `stage_validators.py` infrastructure.

**Deliverables:**
- `BoardState` gains:
  - `constraint_model: Optional["ConstraintModel"] = None`
  - `sat_variable_map: Optional[dict[str, Any]] = None`
  - `topological_solution: Optional["TopologicalSolution"] = None`
  - `assignment_valid: Optional[bool] = None`
  - `topology_graph: Optional["TopologyGraph"] = None`
- New `TYPE_CHECKING` imports in `state.py` for `ConstraintModel`, `TopologicalSolution`, `TopologyGraph`
- Registration entries in `stage_validators.py` for the 5 new stage names

**Dependencies:** `deterministic/state.py`, `deterministic/stages/base.py`, `router_v6/stage_validators.py`

**Validation:** Existing DeterministicPipeline tests pass with new optional-None fields. `dataclasses.replace(state, constraint_model=...)` produces a valid BoardState.

---

### U1. ConstraintGenerationStage

**What:** Extract `ModelBuilder.build()` (lines 391-402 of `_run_stage3`) into a `Stage` subclass.

**Stage class:** `ConstraintGenerationStage` in `router_v6/constraint_model.py`
- `name = "ConstraintGeneration"`
- `run(state)`: reads `state.channel_skeletons` (from Stage 2), `state._parsed_pcb` (for nets + design_rules), `state.channel_widths` (from Stage 2); constructs `ModelBuilder(...)` and calls `.build()`; returns `replace(state, constraint_model=...)`

**Validators** (via `@register_validator("ConstraintGeneration")`):
- `constraint_model.variable_count > 0` when nets present
- Channel variables created for every skeleton edge on every layer
- No variable name collisions in `net_channel_vars`
- Via variables created for every unique skeleton node

**Golden fixture:** `tests/fixtures/stage3_goldens/{board}/constraint_model.json`

**PBT:** For any set of nets with terminal positions, every net-channel variable maps to an actual edge in the skeleton. Net count * edge count * layer count == channel variable count.

**Coverage target:** `temper_placer.router_v6.constraint_model` >= 90% line coverage

**Extraction order:** 1st (no upstream Stage 3 dependency; reads Stage 2 fields)

---

### U2. VariableMappingStage

**What:** Extract `populate_sat_from_constraints` (lines 407-413 of `_run_stage3`) into a `Stage` subclass.

**Stage class:** `VariableMappingStage` in `router_v6/sat_model.py`
- `name = "VariableMapping"`
- `run(state)`: reads `state.constraint_model`, `state._parsed_pcb` (for net_names); calls `build_sat_model()` then `populate_sat_from_constraints(sat_model, constraint_model, net_names)`; returns `replace(state, sat_variable_map=...)`

**Validators** (via `@register_validator("VariableMapping")`):
- Every NetChannelVar in constraint model maps to exactly one SAT variable
- No SAT variable has an empty name
- Variable names are unique within the SAT model
- Connectivity constraint added for every net with channel variables

**Golden fixture:** `tests/fixtures/stage3_goldens/{board}/sat_model.json`

**PBT:** SAT variable count >= constraint model variable count. Every SAT clause references existing variables. For any net, the connectivity clause includes all of that net's channel variables.

**Coverage target:** `temper_placer.router_v6.sat_model` >= 90% line coverage

**Extraction order:** 2nd (depends on constraint_model)

---

### U3. SATSolveStage

**What:** Extract `solve_topology(sat_model, timeout_ms=5000.0)` (lines 420-423 of `_run_stage3`) into a `Stage` subclass.

**Stage class:** `SATSolveStage` in `router_v6/topology_solver.py`
- `name = "SATSolve"`
- `run(state)`: reads `state.sat_variable_map` (the populated SAT model); calls `solve_topology(sat_model, timeout_ms=5000.0)`; returns `replace(state, topological_solution=...)`

**Validators** (via `@register_validator("SATSolve")`):
- `topological_solution.status` is one of {SATISFIABLE, UNSATISFIABLE, UNKNOWN}
- `topological_solution.solver_time_ms < timeout_ms + 100` (solver didn't exceed timeout by more than 100ms)
- If SATISFIABLE, `assignment` is non-empty when variables exist

**Golden fixture:** `tests/fixtures/stage3_goldens/{board}/topological_solution.json`

**PBT:** For an empty SAT model, `satisfiable == True` with empty assignment. For a model with exactly one variable and one positive unit clause, that variable must be True. UNSAT detection: a model with (x) and (¬x) must return UNSATISFIABLE.

**Coverage target:** `temper_placer.router_v6.topology_solver` >= 90% line coverage

**Extraction order:** 3rd (depends on sat_model being populated)

---

### U4. AssignmentValidationStage

**What:** Extract `_check_assignment` (`topology_solver.py:144-169`) as a standalone validation gate between SAT solve and model extraction.

**Stage class:** `AssignmentValidationStage` in `router_v6/topology_solver.py`
- `name = "AssignmentValidation"`
- `run(state)`: reads `state.topological_solution` (assignment), `state.sat_variable_map` (model); calls `_check_assignment(sat_model, solution.assignment)`; stores result in `replace(state, assignment_valid=bool_result)`
- If assignment is invalid, sets `assignment_valid = False` — this gates model extraction from consuming a malformed solution

**Validators** (via `@register_validator("AssignmentValidation")`):
- If `topological_solution.status == SATISFIABLE`, then `assignment_valid == True`
- If `assignment_valid == False`, no subsequent topology extraction should proceed (detected via orchestrator barrier)

**Golden fixture:** `tests/fixtures/stage3_goldens/{board}/assignment_validation.json`

**PBT:** Any assignment satisfying all clauses validates to True. Any assignment missing required connectivity validates to False. Empty assignment on model with unit clause (x) validates to False.

**Coverage target:** `temper_placer.router_v6.topology_solver` >= 90% (shared module with U3)

**Extraction order:** 4th (depends on topological_solution + sat_model)

---

### U5. ModelExtractionStage

**What:** Extract `extract_topology_solution(solution, net_names)` (lines 432-435 of `_run_stage3`) into a `Stage` subclass.

**Stage class:** `ModelExtractionStage` in `router_v6/topology_extraction.py`
- `name = "ModelExtraction"`
- `run(state)`: reads `state.topological_solution`, `state._parsed_pcb` (for net_names), `state.assignment_valid`; if `assignment_valid == False`, skips extraction (returns state unchanged); otherwise calls `extract_topology_solution(solution, net_names)`; returns `replace(state, topology_graph=...)`

**Validators** (via `@register_validator("ModelExtraction")`):
- `topology_graph.routed_net_count <= total net count` (can't route nets not in netlist)
- Every `uses_channels` channel ID references an existing skeleton edge
- `path_graph` nodes are valid string node IDs (not empty, not placeholder)
- If solution is UNSATISFIABLE, `routed_net_count == 0`

**Golden fixture:** `tests/fixtures/stage3_goldens/{board}/topology_graph.json`

**PBT:** SATISFIABLE solution produces `routed_net_count >= 1` when nets exist. UNSATISFIABLE solution produces empty topology. Every node in `path_graph` appears in at least one channel ID.

**Coverage target:** `temper_placer.router_v6.topology_extraction` >= 90% line coverage

**Extraction order:** 5th (depends on topological_solution + assignment_valid)

---

### U6. Stage3Orchestrator and Monolith Adapter

**What:** Build the `Stage3Orchestrator` that chains U1–U5 in dependency order, and refactor `_run_stage3` to use it.

**Deliverables:**
- `Stage3Orchestrator` class in a new `router_v6/stage3_orchestrator.py`:
  ```python
  class Stage3Orchestrator:
      _stages: list[Stage]
      def run(self, pcb: ParsedPCB, stage2: Stage2Output,
              initial_state: BoardState) -> BoardState: ...
  ```
  Chains: ConstraintGeneration -> VariableMapping -> SATSolve -> AssignmentValidation -> ModelExtraction
  Each stage calls `state = stage.run(state)`; DRC validators run after each stage via `VALIDATOR_REGISTRY`.

- Refactored `_run_stage3` (`pipeline.py:388-442`):
  1. Construct initial `BoardState` from upstream fields (channel_skeletons, channel_widths, parsed_pcb)
  2. Run `Stage3Orchestrator.run(pcb, stage2, initial_state)`
  3. Assemble `Stage3Output` from final `BoardState` fields
  4. Preserve verbose-logging lines (gated on `self.verbose`)

- Backward-compatibility adapter: `Stage3Output` assembly reads exactly the 4 fields from BoardState (`constraint_model`, `sat_model`, `solution`, `topology_graph`). Stage 4 accesses `stage3.topology_graph` and `stage3.solution.is_satisfiable` — both present.

**Performance regression test:** `test_stage3_monolith_parity.py` benchmarks wall-clock time of old `_run_stage3` vs `Stage3Orchestrator` on all 4 canonical boards, asserts <5% overhead.

---

### U7. Golden Fixture Generation Script and Parity Tests

**What:** Script to generate committed JSON fixtures, and two parity test files.

**Deliverables:**
- `tests/router_v6/generate_stage3_goldens.py`:
  - Runs `Stage3Orchestrator` on each of the 4 canonical boards (Piantor_Right, LibreSolar_BMS, RP2040_DesignGuide, BitAxe_Ultra)
  - Captures per-sub-step output as JSON under `tests/fixtures/stage3_goldens/{board_name}/{stage_name}.json`
  - Runs each micro-stage individually (feeding intermediate BoardState) so each fixture isolates one sub-step
  - `--regenerate` flag for intentional algorithm changes
  - Custom JSON encoders: SAT variable -> dict, SAT clause -> dict of literals, NetworkX graph -> `node_link_data`, TopologicalSolution -> dict

- `tests/router_v6/test_stage3_golden_parity.py`:
  - Loads each fixture and asserts the corresponding micro-stage produces identical output
  - Tolerances: exact integer equality for variable/clause counts, exact dict equality for assignment, 1e-6 for solver time
  - Runs in CI only on commits touching Stage 3 modules (path-filtered)

- `tests/router_v6/test_stage3_monolith_parity.py`:
  - Runs full `_run_stage3` monolith and `Stage3Orchestrator` on each canonical board
  - Asserts `Stage3Output` field-by-field equality
  - Per-stage parity: separate test per sub-step
  - Performance regression: asserts <5% wall-clock overhead
  - Runs in CI on every push

---

### U8. PBT Suites (One per Micro-Stage)

**What:** Hypothesis-based property test suites for each of the 5 micro-stages.

**Deliverables (5 test files):**
- `tests/router_v6/test_constraint_generation_pbt.py`
- `tests/router_v6/test_variable_mapping_pbt.py`
- `tests/router_v6/test_sat_solve_pbt.py`
- `tests/router_v6/test_assignment_validation_pbt.py`
- `tests/router_v6/test_model_extraction_pbt.py`

Each suite:
- Runs >=100 random examples per strategy (`@settings(max_examples=100)`)
- Registered in CI with 30-second timeout
- Uses `@composite` strategies for SAT model inputs where needed
- Catches a deliberately introduced invariant violation during development

---

### U9. Per-Module Coverage Gate

**What:** CI gate ensuring each Stage 3 module achieves >=90% line coverage independently.

**Deliverable:** CI configuration addition (pytest invocation per module):
```bash
pytest tests/router_v6/test_constraint_model.py tests/router_v6/test_constraint_generation_pbt.py \
  --cov=temper_placer.router_v6.constraint_model --cov-fail-under=90
```
Repeated for each of the 5 modules. Enforced on every push touching any Stage 3 module.

**Modules and existing tests:**
| Module | Existing Tests | New PBT |
|--------|---------------|---------|
| `constraint_model` | `test_constraint_model.py` | `test_constraint_generation_pbt.py` |
| `sat_model` | `test_sat_model.py` | `test_variable_mapping_pbt.py` |
| `topology_solver` | `test_topology_solver.py` | `test_sat_solve_pbt.py`, `test_assignment_validation_pbt.py` |
| `topology_extraction` | `test_topology_extraction.py` | `test_model_extraction_pbt.py` |

---

## Extraction Order and Gating

| Step | Unit | Depends On | Gate to Pass Before Next |
|------|------|-----------|--------------------------|
| 0 | U0 (BoardState + validators) | — | Existing DeterministicPipeline tests pass |
| 1 | U1 (ConstraintGeneration) | U0 | Coverage >= 90%, golden parity, DRC gate |
| 2 | U2 (VariableMapping) | U1 | U1 passes + U2 coverage >= 90%, PBT, DRC |
| 3 | U3 (SATSolve) | U2 | U3 coverage >= 90%, golden parity, PBT, DRC |
| 4 | U4 (AssignmentValidation) | U3 | U4 coverage >= 90%, golden parity, PBT, DRC |
| 5 | U5 (ModelExtraction) | U4 | U5 coverage >= 90%, golden parity, PBT, DRC |
| 6 | U6 (Orchestrator) | U1–U5 | U7 monolith parity passes on all 4 boards |
| 7 | U7 (Golden fixtures + parity) | U6 | All golden diffs = 0; monolith parity = pass |
| 8 | U8 (PBT suites) | U1–U5 | All 5 PBT suites >=100 examples and pass |
| 9 | U9 (Coverage gates) | U8 | All 5 modules >=90% in CI |

Steps 1–5 must be implemented sequentially (the DAG is strictly linear — no parallel extraction possible as in Stage 2). This differs from Stage 2 where U2/U3 and U5/U7 could be parallelized.

---

## Dependencies

- `packages/temper-placer/src/temper_placer/deterministic/stages/base.py` — `Stage(ABC)` protocol (already extended for Stage 2)
- `packages/temper-placer/src/temper_placer/deterministic/state.py` — `BoardState` frozen dataclass (5 new fields added; already has Stage 2 fields populated)
- `packages/temper-placer/src/temper_placer/router_v6/constraint_model.py` — `ModelBuilder`, `ConstraintModel`, `NetChannelVar`, `ViaVar`, `CapacityConstraint`, `DiffPairConstraint`, `LayerConstraint`
- `packages/temper-placer/src/temper_placer/router_v6/sat_model.py` — `SATModel`, `SATVariable`, `SATClause`, `build_sat_model`, `populate_sat_from_constraints`
- `packages/temper-placer/src/temper_placer/router_v6/topology_solver.py` — `solve_topology`, `_check_assignment`, `TopologicalSolution`, `SolverStatus`
- `packages/temper-placer/src/temper_placer/router_v6/topology_extraction.py` — `extract_topology_solution`, `TopologyGraph`, `NetTopology`
- `packages/temper-placer/src/temper_placer/router_v6/pipeline.py` — `_run_stage3`, `Stage3Output`, `RouterV6Pipeline` (refactored `_run_stage3` only)
- `packages/temper-placer/src/temper_placer/router_v6/stage_validators.py` — existing `StageDRCFailure`, `VALIDATOR_REGISTRY`, `@register_validator` (from Stage 2 U0)
- `packages/temper-placer/src/temper_placer/router_v6/stage2_orchestrator.py` — `Stage2Orchestrator` (pattern reference; Stage 3 orchestrator follows same structure)
- `packages/temper-placer/src/temper_placer/router_v6/test_boards.py` — `TEST_BOARDS` with 4 canonical boards
- Existing test files: `test_constraint_model.py`, `test_sat_model.py`, `test_topology_solver.py`, `test_topology_extraction.py`

---

## Assumptions

1. **BoardState fields can be extended without breaking the DeterministicPipeline.** BoardState already has 8 Stage 2 fields + 2 bridge fields (`_parsed_pcb`, `_escape_vias`). Adding 5 Stage 3 optional-None fields follows the same proven pattern.

2. **The 4 canonical test boards are representative.** Piantor_Right (digital, 2L, 33 nets), LibreSolar_BMS (power, 4L, 200 nets), RP2040_DesignGuide (mixed, 4L, 120 nets), BitAxe_Ultra (mixed, 2L, 80 nets) span digital, power, and mixed-signal domains. If golden fixtures match on all 4, the extraction is correct.

3. **Existing module-level functions are pure enough to wrap.** They read arguments, compute, return dataclasses — no global state mutation, disk I/O, or external service dependencies.

4. **The `_run_stage3` ordering is the correct dependency DAG.** Constraint model -> variable mapping -> SAT solve -> assignment validation -> model extraction is the natural dependency order. Verified by reading `_run_stage3`: each step's output is the next step's input.

5. **`hypothesis` and `pytest-cov` are available.** Confirmed in `pyproject.toml`: `hypothesis>=6.0.0`, `pytest-cov>=4.1.0`, `pytest>=7.4.0`.

6. **Serialization to JSON is feasible.** SAT models and variables serialize to dicts. TopologicalSolution serializes to dict (status string, assignment dict, solver_time). TopologyGraph serializes NetTopology dict with node_link_data for path_graphs. Custom JSON encoder handles all.

7. **`_run_stage4` field access is bounded.** Verified: Stage 4 accesses `stage3.topology_graph` (for channel mapping) and `stage3.solution.is_satisfiable` (for fallback logic). The backward-compatibility adapter only needs to populate these 2 fields; the other 2 fields (`constraint_model`, `sat_model`) are present in `Stage3Output` but not consumed downstream.

8. **Parity test runs in <60 seconds in CI.** Constraint generation and SAT solving may take seconds per board (5s timeout), but A* downstream stages are not invoked. The parity test runs only `_run_stage3` monolith + `Stage3Orchestrator`.

9. **AssignmentValidationStage exists primarily as a gating sub-step.** In the monolith, `_check_assignment` is called only internally by `solve_topology` to verify the heuristic solution. Extracting it as a standalone stage enables independent testing, a DRC fence before model extraction, and future integration with a real SAT solver that produces assignments directly.

10. **The simplified SAT solver (round-robin heuristic) is the current production backend.** No real SAT solver (Z3, MiniSat) is integrated. The micro-stages wrap the existing simplified solver — replacing it with a real solver later would only touch the SATSolveStage, not the orchestrator or upstream/downstream stages.

---

## Open Questions

### Unresolved (for implementation phase)

- **[U2][Technical]** `populate_sat_from_constraints` modifies `sat_model` in-place (mutates the empty model created by `build_sat_model()`). The VariableMappingStage must construct the SAT model inside `run()` and return it. Need to verify that the `SATModel` is fully serializable to dict for golden fixtures.

- **[U3][Technical]** `solve_topology` internally calls `_check_assignment` at each heuristic step. With U4 (AssignmentValidationStage) added as a separate stage, the solver may redundantly validate. Resolution: either keep both (belt + suspenders) or modify `solve_topology` to accept a `skip_internal_validation: bool = False` parameter when used within the orchestrator.

- **[U5][Needs research]** `topology_extraction.py` parses variable names to reconstruct topology (string splitting on `route_`/`uses_` prefixes). This parsing logic is fragile — if the SAT variable naming convention in `populate_sat_from_constraints` changes, extraction silently returns empty topology. Resolution during U5: add golden fixture for a known assignment producing known topology, making naming changes detectable.

- **[U7][Needs research]** Are the 4 canonical boards' `.kicad_pcb` fixture files present at `tests/fixtures/external/.cache/`? The `test_boards.py` defines `get_available_boards()` — confirm all 4 `exists()` returns True before writing the golden generation script. Same open question as Stage 2 U10.

- **[U8][Needs research]** What `hypothesis` strategies produce valid SAT models for PBT? Strategies need to generate `SATVariable`, `SATClause` lists, and `TopologicalSolution` assignments. These are pure data structures (no geometry) — simpler than Stage 2's geometric PBT strategies.

- **[U9][Process]** Exact `pytest-cov` invocation for per-module coverage gate. `topology_solver.py` hosts both U3 (SATSolveStage) and U4 (AssignmentValidationStage) — coverage is measured at the module level (both stages together), which is acceptable since both map to the same module.

- **[U2][Scope]** `populate_sat_from_constraints` also adds connectivity clauses (Step 1.5, sat_model.py:152-161) — these are part of variable mapping, not a separate sub-step. The mapping stage's name "VariableMapping" encompasses both variable creation and connectivity constraint addition.

---

## Success Criteria

- **SC1.** `Stage3Orchestrator` produces `Stage3Output` identical to the monolith's `_run_stage3` on all 4 canonical test boards (U7 monolith parity test passes)
- **SC2.** Each of the 5 micro-stage modules reaches >=90% line coverage (U9 coverage gates pass in CI)
- **SC3.** The golden fixture test (U7) diffs exactly 0 on all 4 boards when no algorithm changes are made
- **SC4.** The per-stage DRC gate catches a deliberately introduced invariant violation (e.g., a constraint model variable without corresponding SAT variable) with a named `StageDRCFailure`
- **SC5.** The PBT suite (U8) runs >=100 examples per stage and catches a deliberately introduced invariant violation (e.g., an assignment that doesn't satisfy all clauses)
- **SC6.** The closure test produces identical `router_completion_pct` and `drc_errors` before and after the decomposition
- **SC7.** Existing tests in `tests/router_v6/test_constraint_model.py`, `test_sat_model.py`, `test_topology_solver.py`, `test_topology_extraction.py` continue to pass
- **SC8.** Performance regression <= 5% wall-clock overhead vs monolith on canonical boards

---

## Risk Analysis

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| BoardState field addition breaks DeterministicPipeline consumers | Low | High | All existing fields use `= None` defaults; deterministic pipeline tests run as gate before any micro-stage lands |
| SAT model in-place mutation incompatible with frozen BoardState | Medium | Medium | `VariableMappingStage` constructs a new SAT model, populates it, and returns a copy to BoardState — no in-place mutation of state fields; verify `SATModel` is deep-copyable via `dataclasses.replace` |
| Simplified solver non-determinism between monolith and micro-stage runs | Medium | Medium | The heuristic solver's random behavior (round-robin with offset) is deterministic given the same input order; golden fixtures lock the output; if non-determinism arises, add seeding |
| Can't run parity test on all 4 boards (missing .kicad_pcb fixtures) | Medium | Medium | Fall back to whatever subset is available; document which boards are tested |
| `hypothesis` strategies for SAT model generation are too slow | Low | Low | SAT models are pure data structures — string and boolean generators are fast; timeout catches issues |
| Per-module coverage gate reveals existing gaps in test coverage | High | Low | This is the point — gaps are filled as part of each U1–U5 implementation |
| Monolith parity breaks due to solver_time_ms float differences | Medium | Low | Golden fixture comparison uses 1e-6 tolerance for float fields; exact comparison for discrete fields |
| Existing `_run_stage3` verbose logging lost in extraction | Low | Low | Orchestrator preserves verbose flag; each stage can accept an optional `verbose: bool` parameter |
| String-parsing topology extraction fragile when variable names change | Medium | High | Golden fixture locks variable naming convention; extraction PBT validates known-name -> known-topology mapping |

---

## Implementation Notes

### Code conventions
- Stage subclasses follow the DeterministicPipeline pattern: `name` property, `run(state: BoardState) -> BoardState` method.
- All module-level functions (`ModelBuilder.build`, `populate_sat_from_constraints`, `solve_topology`, `_check_assignment`, `extract_topology_solution`) remain unchanged and callable directly.
- DRC validators are standalone functions decorated with `@register_validator("StageName")`, not methods.
- Golden fixtures use JSON with custom encoder (SAT var/clause as dicts, networkx `node_link_data`, TopologicalSolution as dict).
- PBT suites use `hypothesis` with `@settings(max_examples=100, deadline=30000)`.
- Verbose logging preserved via orchestrator flag propagation.

### File listing
```
packages/temper-placer/src/temper_placer/
  deterministic/
    state.py                          # +5 fields (MODIFY)
  router_v6/
    stage_validators.py               # +5 validator registrations (MODIFY)
    stage3_orchestrator.py            # NEW: Stage3Orchestrator
    constraint_model.py               # +ConstraintGenerationStage class (MODIFY)
    sat_model.py                      # +VariableMappingStage class (MODIFY)
    topology_solver.py                # +SATSolveStage, +AssignmentValidationStage classes (MODIFY)
    topology_extraction.py            # +ModelExtractionStage class (MODIFY)
    pipeline.py                       # _run_stage3 refactored (MODIFY)

packages/temper-placer/tests/
  fixtures/stage3_goldens/
    {board_name}/
      constraint_model.json           # NEW: golden fixture
      sat_model.json                  # NEW
      topological_solution.json       # NEW
      assignment_validation.json      # NEW
      topology_graph.json             # NEW
  router_v6/
    test_stage3_golden_parity.py      # NEW
    test_stage3_monolith_parity.py    # NEW
    generate_stage3_goldens.py        # NEW
    test_constraint_generation_pbt.py  # NEW
    test_variable_mapping_pbt.py      # NEW
    test_sat_solve_pbt.py             # NEW
    test_assignment_validation_pbt.py # NEW
    test_model_extraction_pbt.py      # NEW
```

### Stage 3 vs Stage 2 comparison

| Aspect | Stage 2 (Channel Analysis) | Stage 3 (SAT Solver) |
|--------|---------------------------|---------------------|
| Sub-steps | 8 | 5 |
| DAG shape | Branching (3 parallelizable) | Linear (sequential only) |
| Data types | Geometry (MultiPolygon, numpy, NetworkX) | Logic (SAT vars, clauses, assignments) |
| PBT complexity | High (geometric strategies) | Medium (data structure strategies) |
| Wall time | ~100ms | ~1-5s (SAT solver dominates) |
| Downstream consumer | Stage 3 (SAT) + Stage 4 (A*) | Stage 4 (A*) only |
| Existing tests | 8 per-module test files | 4 per-module test files |

Stage 3 decomposition is objectively simpler than Stage 2: fewer sub-steps, strictly linear DAG, no geometry-heavy fixtures, and all supporting infrastructure (Stage protocol, `@register_validator`, golden fixture format, CI gate pattern, `Stage3Output` adapter) already demonstrated working.

---

## Reference: Stage 3 Monolith Code

For implementation reference, the current monolithic `_run_stage3` in `pipeline.py:388-442`:

```python
def _run_stage3(self, pcb: ParsedPCB, stage2: Stage2Output) -> Stage3Output:
    # 3.1-3.6: Build constraint model
    model_builder = ModelBuilder(
        skeletons=stage2.skeletons, nets=pcb.nets,
        channel_widths=stage2.channel_widths, design_rules=pcb.design_rules,
        diff_pairs=[], pcb=pcb)
    constraint_model = model_builder.build()

    # 3.7: Build SAT model
    sat_model = build_sat_model()
    net_names = [net.name for net in pcb.nets]
    populate_sat_from_constraints(sat_model, constraint_model, net_names)

    # 3.8: Solve topology
    solution = solve_topology(sat_model, timeout_ms=5000.0)

    # 3.9: Extract topology
    topology_graph = extract_topology_solution(solution, net_names)

    return Stage3Output(
        constraint_model=constraint_model, sat_model=sat_model,
        solution=solution, topology_graph=topology_graph)
```
