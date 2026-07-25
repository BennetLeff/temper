---
type: feat
origin: docs/brainstorms/2026-07-05-jax-retirement-production-rollback-requirements.md
status: abandoned
swept: 2026-07-25
swept_basis: "only 1/33 named paths exist"
---
# feat: JAX Retirement — Reverse-Topological Deletion

## Summary

Delete the JAX descent stack (optimizer, losses, placement, loss_bridge, force-directed heuristics), close five placement-init worktrees, surface `--placer jax-deprecated` as a no-op deprecation warning, and resolve the PlacementState JAX coupling. Decisive result: deletion PR lands green, CP-SAT is the sole default placer, and `--placer jax-deprecated` exists as a one-cycle UX placeholder.

**Scale:** 73 files to delete, ~37 files importing PlacementState, 82+ files with JAX imports to modify or remove, 2 library consumers of `_resolve_to_indices` to relocate, 1 CLI flag to create from scratch.

---

## Problem Frame

The CP-SAT feasibility spike (652/652 audit pass) and the paradigm-swap decision settle the technical and strategic questions. The deletion PR closes the gap between the strategic decision and codebase state. Per the umbrella's Decisive-Result-Discipline, no parity number gates this; the deletion PR's green CI status and CP-SAT-as-default are the decision's evidence.

Prior framings overridden: the original U9's parity-gate bridge, and the brainstorm-doc's parity-skip. Current framing: the rollback window becomes "production-rollback for non-corpus boards" with the same one-release-cycle duration but a different justification.

---

## Implementation Units

### U1. Relocate `_resolve_to_indices` from `loss_bridge.py`

**Goal:** Extract `_resolve_to_indices` to a surviving module before `loss_bridge.py` is deleted. This pure-Python utility is imported by `sat_bridge.py:109` and `parser.py:82`.

**Requirements:** R1 (deletion must not break SAT bridge or PCL parser)

**Dependencies:** None — run first, before any directory-level deletions.

**Files:**
- Create: `src/temper_placer/pcl/resolver.py` (new home for `_resolve_to_indices`)
- Modify: `src/temper_placer/pcl/loss_bridge.py` (remove function, re-export from new location via deprecation shim)
- Modify: `src/temper_placer/pcl/sat_bridge.py` (update import to `pcl.resolver`)
- Modify: `src/temper_placer/pcl/parser.py` (update import to `pcl.resolver`)

**Approach:** Extract `_resolve_to_indices` and its helper `_parse_reference` to `pcl/resolver.py`. In `loss_bridge.py`, replace the function body with a re-export: `from temper_placer.pcl.resolver import _resolve_to_indices` to keep the deletion unit atomic — consumers first, then delete the bridge in U3.

**Patterns to follow:** `docs/solutions/architecture-patterns/pad-position-ssot-placer-2026-06-28.md` — mechanical import-path migration without logic change.

**Test scenarios:**
- `_resolve_to_indices("Q1", netlist, board)` returns `[0]` for a single-component ref
- `_resolve_to_indices("HV_ZONE", netlist, board)` returns component indices within the zone
- `_resolve_to_indices("nonexistent", netlist, board)` raises `ValueError` with descriptive message
- Import from `pcl.resolver` is functional (sat_bridge and parser integration tests pass)

**Verification:** `sat_bridge.py` and `parser.py` imports resolve; existing PCL parser tests pass.

---

### U2. Build Full Import Dependency Graph and Deletion Order

**Goal:** Produce the complete reverse-topological deletion order — every file that directly or transitively imports from the five deletion targets, ordered so leaf files delete first and core files last.

**Requirements:** R1 (complete deletion, no dangling imports)

**Dependencies:** U1 (_resolve_to_indices already safe)

**Files:**
- Read only: all files under `src/temper_placer/` (analysis, not modification)
- The dependency graph is an artifact, not a committed file — store the deletion order as an inline list in this plan or in a `DELETION_ORDER.md` scratch file

**Approach:** Per the dead-code-deletion pattern (`docs/solutions/architecture-patterns/dead-code-deletion-dependency-graph-strangler-2026-06-28.md`):
1. Run `rg "from temper_placer\.(optimizer|losses|placement|heuristics\.force_directed)|from temper_placer\.pcl\.loss_bridge" src/temper_placer/ -l` to identify all consumers
2. Run `rg "import jax|from jax|import optax|import flax" src/temper_placer/ -l` for the wider JAX dependency surface
3. Classify each consumer: delete-entirely (leaf, no JAX-free dependents), modify (has surviving callers or shares the file with non-JAX code), keep-as-is (JAX-free, no imports from deleted modules)
4. Topological-sort the delete-entirely list: leaf files first, then support files, then verifiers, then core directories

**Test scenarios:**
- Every import path in the deletion scope has a known consumer (no orphaned imports)
- Every consumer is classified (delete / modify / keep) with rationale
- The deletion order is reverse-topological (no file deleted before its last importer)

**Verification:** `rg` after the full deletion returns zero matches for `optimizer|losses|placement\.legalization|heuristics\.force_directed|loss_bridge` in `src/temper_placer/`.

---

### U3. Delete JAX-Core Directories and File (Leaf-to-Root)

**Goal:** Execute the deletion in reverse-topological order: delete the five directories/files that are the JAX core, after ensuring all consumers are ported or classified.

**Requirements:** R1, R4 (deletion PR green, CP-SAT sole default)

**Dependencies:** U1, U2 (consumers identified and prepared)

**Files:**
- Delete: `src/temper_placer/optimizer/` (21 files)
- Delete: `src/temper_placer/losses/` (43 files including `physics/` subpackage)
- Delete: `src/temper_placer/placement/` (7 files — including `legalization.py` which `router_v6/pipeline.py` imports)
- Delete: `src/temper_placer/pcl/loss_bridge.py` (549 lines — `_resolve_to_indices` already relocated in U1)
- Delete: `src/temper_placer/heuristics/force_directed.py` (473 lines)

**Approach:** Use `git rm -r` for each directory/file once its consumers are ported. Delete in the order: `force_directed.py` → `loss_bridge.py` → `losses/` → `placement/` → `optimizer/`. Each sub-unit is a commit that passes CI independently. The `router_v6/pipeline.py` import of `Legalizer` from `placement/legalization.py` must be resolved before deleting `placement/`: either replace the Legalizer call with a no-op (if it was JAX-only collision fixup) or port the relevant logic.

**Patterns to follow:** `docs/solutions/architecture-patterns/dead-code-deletion-dependency-graph-strangler-2026-06-28.md` — each deletion commit passes CI independently.

**Test scenarios:**
- After each sub-unit deletion: `pytest` in affected test directories passes
- After all deletions: `rg "from temper_placer\.optimizer" src/` returns zero matches
- After all deletions: `rg "from temper_placer\.losses" src/` returns zero matches
- After all deletions: `rg "from temper_placer\.placement\." src/` returns zero matches (except allowed references in configs/docs)
- Covers AE4. The 5,209-test collection passes with JAX-only tests removed.

**Verification:** `git diff --stat` shows 73 files deleted; `rg` verification grep returns zero matches.

---

### U4. Modify Pipeline Orchestrator and Stages

**Goal:** Replace JAX-dependent pipeline stages with CP-SAT invocation, remove JAX imports from `orchestrator.py` and stage files, and update docstrings.

**Requirements:** R1, R4, AE1 (temper optimize runs CP-SAT by default, no JAX path reachable)

**Dependencies:** U3 (JAX core deleted, no import conflicts)

**Files:**
- Modify: `src/temper_placer/pipeline/orchestrator.py` — remove `import jax.numpy as jnp` (line 28), remove inline `import jax`/`import optax` (lines 445-448, 508, 523, 574-575), remove `@jax.jit` decorators, remove `jax.value_and_grad` calls, replace geometric stage dispatch with CP-SAT invocation
- Modify: `src/temper_placer/pipeline/stages/geometric_stage.py` — replace JAX optimization loop with CP-SAT solve dispatch
- Modify: `src/temper_placer/pipeline/stages/refinement_stage.py` — remove JAX import (line referenced uses `import jax.numpy`)
- Modify: `src/temper_placer/pipeline/stages/routing_stage.py` — remove JAX import
- Modify: `src/temper_placer/pipeline/stages/thermal_anchoring_stage.py` — remove JAX import
- Modify: `src/temper_placer/pipeline/stages/output_stage.py` — remove JAX import
- Modify: `src/temper_placer/pipeline/geometric.py` — remove JAX imports

**Approach:** The pipeline's geometric stage currently runs JAX gradient descent via `optax.adam`. Replace with a CP-SAT placement dispatch — the CP-SAT placer (from the existing `placer/` or the constraint-completion workstream's encoder) produces a `PlacementResult`. Non-JAX pipeline stages (routing, output) stay intact but must remove their JAX import lines. The `temper optimize` CLI command (line 237 of `cli/__init__.py`) must route through the non-JAX pipeline.

**Patterns to follow:** Existing `placer/deterministic.py` `PlacementResult` dataclass for output shape.

**Test scenarios:**
- `temper optimize temper.kicad_pcb --config pcl/temper_induction.yaml` completes without JAX import errors
- Pipeline DAG runs all non-geometric stages after CP-SAT placement
- Covers AE1. CP-SAT runs by default, no JAX path reachable.

**Verification:** `rg "import jax" src/temper_placer/pipeline/` returns zero matches; `temper optimize` runs end-to-end with CP-SAT.

---

### U5. Decouple PlacementState from JAX

**Goal:** Replace `PlacementState`'s JAX `Array` fields (`positions`, `rotation_logits`, `net_virtual_nodes`) with numpy/plain-Python equivalents, or create a JAX-free `PlacementState` constructor path for the CP-SAT output. This is the single highest-risk refactor — 37 importing files.

**Requirements:** R1, R4 (PlacementState survives deletion and is usable by CP-SAT output path)

**Dependencies:** U3 (JAX deleted; PlacementState must be importable without JAX)

**Files:**
- Modify: `src/temper_placer/core/state.py` — remove `import jax` (line 14), `import jax.numpy as jnp` (line 15), `from jax import Array` (line 16); replace `Array` type hints with `numpy.ndarray`; remove `random_init()` and `sample_rotation()` JAX-dependent methods; add `from_positions_dict(dict[str, tuple[float, float]]) -> PlacementState` factory
- Modify: 37 files importing `PlacementState` — update any code that accesses `positions` as JAX `Array` (most will work with numpy as drop-in); remove callers of `random_init()` and `sample_rotation()`

**Approach:** Per the `pad-position-ssot` pattern (`docs/solutions/architecture-patterns/pad-position-ssot-placer-2026-06-28.md`): replace JAX-dependent attributes with pure-Python equivalents. The key insight from that learning: "replace JAX-dependent methods with pure-Python free functions." Two parallel strategies:
1. **JAX-free representation path:** Add a `from_positions_dict()` factory that accepts `dict[str, tuple[float, float]]` and populates a numpy-backed `PlacementState`. This is the CP-SAT output path.
2. **Stub JAX methods for deletion:** Replace `random_init()`, `sample_rotation()`, `get_rotation_angles()`, `get_rotations()`, and `to_discrete()` with stubs that raise `NotImplementedError` — these were JAX-only initialization/rotation utilities that CP-SAT replaces. The `rotation_logits` field is removed; rotation state moves to `PlacementResult.rotations: NDArray[np.int32]`.

**Note:** The full `_from_netlist_and_board` path also uses JAX and must be replaced. The CP-SAT placement workflow uses `PlacementResult` from `placer/deterministic.py` instead.

**Patterns to follow:** `docs/solutions/architecture-patterns/pad-position-ssot-placer-2026-06-28.md`

**Test scenarios:**
- `PlacementState.from_positions_dict({"Q1": (10.0, 20.0), "Q2": (30.0, 40.0)})` returns a valid PlacementState
- `PlacementState.__init__` accepts `numpy.ndarray` for positions field (no JAX Array requirement)
- Existing consumers that read `positions` as an array continue to work (numpy is API-compatible for indexing)
- `temper optimize` produces a PlacementState that is consumed by downstream stages
- All 37 importing files pass their existing tests after the migration

**Verification:** `rg "import jax" src/temper_placer/core/state.py` returns zero matches; 37 importing files pass tests.

---

### U6. Remove JAX from CLI and Supporting Modules

**Goal:** Remove JAX imports from CLI entry points, adapters, regression runners, validation, and other supporting modules that don't need JAX post-deletion.

**Requirements:** R1, AE1, AE4

**Dependencies:** U4, U5 (pipeline and PlacementState are JAX-free)

**Files:**
- Modify: `src/temper_placer/cli/__init__.py` — remove `constraint_to_loss` import from `loss_bridge.py` (line 726); remove any JAX-related CLI commands
- Modify: `src/temper_placer/cli/pipeline_commands.py` — remove JAX imports
- Modify: `src/temper_placer/regression/corpus_runner.py` — remove JAX imports
- Modify: `src/temper_placer/regression/multi_seed_experiment.py` — remove or delete (JAX-only experiment)
- Modify: `src/temper_placer/regression/physics_oracle.py` — remove JAX imports; `run_physics_oracle` must be refactored (calls `train_multiphase` from deleted `optimizer.train`)
- Modify: `src/temper_placer/validation/geometric.py` — remove JAX imports
- Modify: `src/temper_placer/validation/drc_oracle.py` — remove JAX imports
- Modify: `src/temper_placer/validation/human_reference_extractor.py` — remove JAX imports
- Modify: `src/temper_placer/validation/metrics.py` — remove JAX imports
- Modify: `src/temper_placer/ablation/runner.py` — remove `import jax` (line 14)
- Delete: `src/temper_placer/ml/` directory (gnn_predictor, learned_init, train_gnn — JAX-only ML training)
- Delete: `src/temper_placer/experiments/` directory (seed_robustness_validation, routability_signal_validation — JAX-only)

**Approach:** Batch-modify import lines; where a module is entirely JAX-dependent (ml/, experiments/), delete it. For `physics_oracle.py`, the `run_physics_oracle` function must be rewritten to call the CP-SAT placer instead of `train_multiphase` — this is a port, not a deletion.

**Test scenarios:**
- `temper optimize` CLI command works (imports resolve, no ImportError)
- `temper pipeline` CLI command works
- Regression corpus runner works without JAX (or is quarantined if dependent)
- Validation module imports resolve
- Ablation runner imports resolve

**Verification:** `rg "import jax" src/temper_placer/cli/` returns zero matches; all CLI commands start without ImportError.

---

### U7. Update the `BaseConstraint.backends` Registry

**Goal:** Remove the JAX backend registration (`backends["jax"]`) from `pcl/constraints.py`, change the default `targets` from `["jax"]` to `["sat"]`, and remove the `tier_to_weight` mapping (JAX loss-weight concept).

**Requirements:** R1 (no JAX compilation path survives)

**Dependencies:** U3 (loss_bridge.py deleted; the backend adapter at line 549 is gone)

**Files:**
- Modify: `src/temper_placer/pcl/constraints.py` — remove `backends["jax"] = None` entry (line 250); change `targets: list[str] = field(default_factory=lambda: ["jax"])` default (line 199)
- Modify: `src/temper_placer/pcl/loss_bridge.py` — already deleted in U3; verify no residue in pcl/__init__.py

**Approach:** The PCL constraint system uses a backend dispatch: each constraint targets `["jax"]` by default, and `loss_bridge.py` registered the JAX adapter. After deletion, the default target should be `["sat"]` (routing SAT solver) or `["cp-sat"]` (the new CP-SAT placer, once the constraint-completion workstream adds its backend). For this workstream, keep `["sat"]` as the default since CP-SAT encoder is delivered by F2.

**Test scenarios:**
- `BaseConstraint()` default targets does not include `"jax"`
- Existing SAT bridge compilation still works (constraints target `["sat"]`)
- PCL parser tests pass without JAX backend

**Verification:** `rg "backends\[.jax.\]" src/` returns zero matches; PCL compilation test suite passes.

---

### U8. Add `--placer jax-deprecated` CLI Flag as No-Op Warning

**Goal:** Add a `--placer` option to the `temper optimize` CLI command. When `--placer jax-deprecated` is passed, print the deprecation warning to stderr and exit. The flag persists for one release cycle.

**Requirements:** R2, AE2

**Dependencies:** U6 (CLI is JAX-free, can accept the flag)

**Files:**
- Modify: `src/temper_placer/cli/__init__.py` — add `--placer` option to the `optimize` command
- Create: `tests/cli/test_placer_flag.py` — integration test through the CLI path

**Approach:** Add `@click.option("--placer", type=click.Choice(["cp-sat", "jax-deprecated"]), default="cp-sat")` to the `optimize` command. When `jax-deprecated` is selected, print to stderr: `"The JAX placer has been removed; CP-SAT is the sole placer. If you reached this flag for production-rollback reasons, file an issue with the board's PCL config and the routed-PCB file."` and exit with code 0 (not an error — informational). Per the silent-guard-condition learning (`docs/solutions/workflow-issues/silent-guard-condition-infrastructure-failure-pattern-2026-07-02.md`): the test must verify A/B divergence — output with `--placer jax-deprecated` is different from without.

**Patterns to follow:** `docs/solutions/workflow-issues/silent-guard-condition-infrastructure-failure-pattern-2026-07-02.md` — A/B comparison test; `docs/solutions/workflow-issues/dead-code-from-features-with-no-activation-surface-2026-07-01.md` — real CLI activation surface.

**Test scenarios:**
- `temper optimize --placer jax-deprecated` prints deprecation warning to stderr and exits code 0
- `temper optimize --placer jax-deprecated` output is byte-different from `temper optimize --placer cp-sat` (A/B divergence)
- `temper optimize --placer cp-sat` (default) proceeds with CP-SAT placement
- Covers AE2. The flag names the production-rollback rationale and exits without crash.

**Verification:** Integration test passes; `--placer jax-deprecated` visible in `temper optimize --help`.

---

### U9. Close Five Placement-Init Worktrees

**Goal:** Close the five `placement-init-*` worktrees without merging. Each closure commit records the rationale.

**Requirements:** R3, AE3

**Dependencies:** U1-U3 (deletion PR is the context; worktree closures can happen same-day)

**Files:**
- No source file changes — git branch management only

**Approach:** Per the worktree-safety learning (`docs/solutions/workflow-issues/silent-source-loss-worktree-parallel-merges-2026-07-01.md`):
1. Record each branch's manifest: `git diff --name-only --diff-filter=ACMR main...$BRANCH`
2. Verify no expected file is missing in HEAD before closing
3. For each worktree: `git worktree remove .worktrees/feat/placement-init-{ccap,dpp,hierarchical,thermal,constraint-passthrough}`
4. Delete the branches: `git branch -D feat/placement-init-{ccap,dpp,hierarchical,thermal,constraint-passthrough}`
5. The `constraint-passthrough` useful payload (`PlacementState.from_positions_dict`) already landed in #121's U5 — verified before closure

**Test scenarios:**
- Covers AE3. `git worktree list` shows no `placement-init-*` branches; remaining worktrees represent the post-swap mental model.

**Verification:** `git worktree list | grep placement-init` returns no matches.

---

### U10. Audit `pyproject.toml` and Remove JAX Dependencies if Clean

**Goal:** If the post-deletion grep returns zero JAX survivors in `src/`, remove JAX/optax/flax from `pyproject.toml`. Otherwise, leave them with a comment noting which files still import JAX and why.

**Requirements:** R1 (scope boundary: in-scope only if grep returns zero survivors)

**Dependencies:** U3-U8 (all deletions and modifications complete)

**Files:**
- Modify: `packages/temper-placer/pyproject.toml` — conditionally remove `jax>=0.4.20`, `jaxlib>=0.4.20`, `optax>=0.1.7`, `flax>=0.7.0`, `jax[cuda12_pip]` from `[project.optional-dependencies] gpu`

**Approach:** Run `rg "import jax|from jax" src/temper_placer/ -l`. If zero matches: remove all four JAX deps and the GPU extra. If matches remain: document which files still need JAX (likely `core/state.py` during the strangler's tail, per the doc's own scope boundary) and leave deps in place with a `# TODO: remove after JAX strangler complete` comment.

**Test scenarios:**
- If JAX deps removed: `uv sync` succeeds; `temper optimize` runs without JAX
- If JAX deps retained: `uv sync` succeeds; comment documents the surviving files
- CI passes in both cases

**Verification:** `pyproject.toml` accurately reflects the post-deletion dependency state.

---

### U11. Update Import-Linter Boundaries and Dead-Code Baselines

**Goal:** Remove JAX-related allowlist entries from `.importlinter`, update Vulture dead-code baselines, and regenerate any CI gate files that reference the deleted modules.

**Requirements:** R1 (CI green)

**Dependencies:** U3-U8 (all deletions and modifications complete)

**Files:**
- Modify: `.importlinter` — remove JAX-related boundary contracts
- Modify: `import-linter-allowlist.yaml` — remove JAX-related entries
- Modify: dead-code baseline files (Vulture allowlist or similar)

**Approach:** After deletions, `import-linter` may flag new violations for removed modules. Clean up allowlist entries in the same commit that deletes the corresponding module — per the dead-code-deletion learning's "monotonic shrink" principle.

**Test scenarios:**
- `uv run python scripts/import_linter_gate.py` passes (no JAX-related violations)
- Dead-code check passes (baseline monotonic shrink)
- CI green

**Verification:** Import-linter and dead-code CI gates pass.

---

## Key Technical Decisions

1. **Delete in reverse-topological order, not `rm -rf`.** The prior router migration deleted 26K lines across 17 atomic PRs using exactly this strategy. Each deletion sub-unit is its own commit that passes CI independently. (see origin: `docs/brainstorms/2026-07-05-jax-retirement-production-rollback-requirements.md`; pattern: `docs/solutions/architecture-patterns/dead-code-deletion-dependency-graph-strangler-2026-06-28.md`)

2. **`PlacementState` JAX decoupling: numpy replacement, not dual-representation.** The `pad-position-ssot` learning proved JAX can be mechanically stripped by replacing Array with numpy and replacing JAX-only methods with pure-Python equivalents. A dual-representation (JAX + non-JAX) adds complexity without benefit — JAX is being deleted. (see origin: Key Decisions — 22 import wraps resolve to real refactors)

3. **`_resolve_to_indices` relocation, not reimplementation.** This pure-Python utility is the sole non-JAX survivor in `loss_bridge.py`. Extracting it to `pcl/resolver.py` before deletion is the lowest-risk path. Reimplementing it would risk behavior drift in SAT bridge and PCL parser.

4. **`--placer jax-deprecated` is a CLI flag, not a placer dispatch.** Per the session-report round-2 finding: the flag can't dispatch JAX after the optimizer is gone. It is a UX placeholder that prints a deprecation warning and exits. The A/B divergence test is the guard against silent-guard-condition failure. (see origin: Key Decisions — no-op deprecation warning, not active rollback dispatch)

5. **`pyproject.toml` JAX removal is gated on post-deletion grep.** If `core/state.py` or `physics_oracle.py` still import JAX during the strangler's tail, JAX stays in deps with a documented comment. Full JAX removal is deferred to the dependency-audit follow-up. (see origin: Key Decisions — JAX dependency audit gated on post-deletion grep)

---

## Scope Boundaries

### Deferred for Later

- `--placer jax-deprecated` post-window removal — tracked under the existing calendar-gate plan's Deferred-to-Follow-Up (see origin)

### Deferred to Follow-Up Work

- Full `pyproject.toml` JAX removal if post-deletion grep finds survivors — documented in U10
- `viz-server` worktree disposition — separate workstream (see origin)
- Any remaining `except ImportError` patterns that referenced JAX modules — migrate to real refactors if discovered post-deletion

### Outside This Product's Identity

- Parity comparison between JAX and CP-SAT placements (see origin: parity is theater)
- JAX/CP-SAT performance benchmarking
- Re-adding JAX as an alternative placer

---

## Dependencies / Prerequisites

- #121 (CP-SAT feasibility-first placer) merged — verified (see origin)
- The reverse-topological deletion list in U9 of `docs/plans/2026-07-03-001-...` is correct and complete — verified during round-1 doc review (see origin)
- `PlacementState.from_positions_dict()` does NOT exist yet — U5 creates it; the origin doc's claim that it "survives deletion" is incorrect (discovered in doc review)
- The `_resolve_to_indices` relocation must precede `loss_bridge.py` deletion — U1 is the first unit

---

## Risks

| Risk | Mitigation |
|------|-----------|
| PlacementState used by 37 files; JAX decoupling breaks downstream consumers silently | U5: test every importing file; mechanical numpy-for-Array replacement where possible; stub JAX-only methods |
| `router_v6/pipeline.py` imports `Legalizer` from to-be-deleted `placement/legalization.py` | U2: classify Legalizer usage — if it was collision-fixup for JAX placements, replace with CP-SAT placement's native collision avoidance |
| `physics_oracle.py` calls `train_multiphase` from deleted `optimizer.train` | U6: rewrite `run_physics_oracle` to dispatch CP-SAT placement instead |
| Worktree closure loses source files (prior incident: thermal anchoring lost `thermal_potential.py`) | U9: file-manifest verification per `docs/solutions/workflow-issues/silent-source-loss-worktree-parallel-merges-2026-07-01.md` before closing |
| `--placer jax-deprecated` is unreachable (silent guard condition) | U8: A/B divergence test verifies the warning actually fires |
| Test suite contains JAX-dependent tests that break after deletion | U3: identify and remove JAX-only tests during deletion; 5,209-test count will decrease — this is expected |

---

## Test Strategy

- **Unit tests:** Every U1-U8 unit has per-unit test scenarios. The PCL resolver, PlacementState migration, and CLI flag each get targeted unit coverage.
- **Integration tests:** U8's `--placer` flag test fires through the CLI surface (not just unit); U5's PlacementState migration test runs through `temper optimize`.
- **Regression:** The existing 5,209-test collection is the CI gate. JAX-only tests are removed; CP-SAT tests and pure-Python tests must continue to pass.
- **A/B divergence:** The `--placer jax-deprecated` test (U8) explicitly verifies the flag produces byte-different output from the default path.

---

## Output Structure

Expected changes to the source tree:

```
src/temper_placer/
├── pcl/
│   ├── resolver.py          (NEW — _resolve_to_indices home)
│   ├── constraints.py       (MODIFY — remove JAX backend registration)
│   ├── loss_bridge.py       (DELETE)
│   └── ...
├── core/
│   └── state.py             (MODIFY — JAX → numpy decoupling)
├── pipeline/
│   ├── orchestrator.py      (MODIFY — remove JAX, dispatch CP-SAT)
│   ├── geometric.py         (MODIFY — remove JAX)
│   └── stages/              (MODIFY — remove JAX from 5 stage files)
├── optimizer/               (DELETE — 21 files)
├── losses/                  (DELETE — 43 files)
├── placement/               (DELETE — 7 files)
├── heuristics/
│   └── force_directed.py    (DELETE)
├── ml/                      (DELETE — 4 files)
├── experiments/             (DELETE — 2 files)
├── cli/
│   └── __init__.py          (MODIFY — add --placer flag)
├── regression/              (MODIFY — 3 files, remove JAX imports)
├── validation/              (MODIFY — 4 files, remove JAX imports)
└── ablation/
    └── runner.py            (MODIFY — remove JAX import)

tests/
└── cli/
    └── test_placer_flag.py  (NEW — integration test for --placer flag)
```
