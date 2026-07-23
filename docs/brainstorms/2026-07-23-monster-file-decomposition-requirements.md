---
date: 2026-07-23
topic: monster-file-decomposition
---

# Monster File Decomposition: Breaking Down 10+ Files Exceeding 1,000 Lines

## Summary

Decompose the 10 largest source files in `temper_placer/` (each exceeding 1,000 lines) into focused modules with clear single responsibilities. Target files include `placer/cp_sat/loop.py` (1,508 lines -- the worst offender), `router_v6/astar_pathfinding.py` (1,452), `router_v6/pipeline.py` (1,422), `io/kicad_parser.py` (1,391), `io/kicad_writer.py` (1,311), `deterministic/stages/phased_component_assignment.py` (1,286), `deterministic/stages/clearance_grid.py` (1,244), `placer/cp_sat/encoder.py` (1,198), `router_v6/adapter.py` (1,127), and `pcl/parser.py` (1,079). The decomposition is guided by class/method boundaries, public-vs-private separation, and test isolation -- not arbitrary line-count targets.

---

## Problem Frame

Ten source files in `temper_placer/` exceed 1,000 lines each. These files concentrate both complexity and coupling: they are the most-changed files in the repo, the hardest to review, and the most likely to harbor bugs in unexercised edge cases.

**Specific costs of each monster file:**

| File (lines) | Primary Problem |
|---|---|
| `placer/cp_sat/loop.py` (1,508) | Monolithic CP-SAT encoding loop. Mixes constraint construction, variable management, solver configuration, and solution extraction in one file. Has inline `@njit` Numba functions alongside OR-Tools CP-SAT calls -- two very different performance models in one module. |
| `router_v6/astar_pathfinding.py` (1,452) | Mixes grid-space A* search, path backtracking, cost heuristics, and conflict resolution. The `_reconstruct_path()`, `_compute_heuristic()`, and grid-marshalling logic are separable concerns. |
| `router_v6/pipeline.py` (1,422) | Orchestrates all router stages (grid prep, net ordering, topology, A*, manufacturing). The pipeline orchestration and per-stage configuration are interleaved. |
| `io/kicad_parser.py` (1,391) | Monolithic KiCad S-expression parser. Parses board, modules, nets, zones, tracks, and vias in one file with deeply nested recursive descent. |
| `io/kicad_writer.py` (1,311) | Monolithic KiCad S-expression writer. The inverse of the parser -- board, module, net, track, and zone serialization in one file. |
| `deterministic/stages/phased_component_assignment.py` (1,286) | Multi-phase component placement logic: zone assignment, rotation optimization, clearance validation, and collision resolution. Each phase is a separable concern. |
| `deterministic/stages/clearance_grid.py` (1,244) | Clearance grid computation with multiple strategies (expanded, conservative, zone-aware). Strategy selection and grid computation are interleaved. |
| `placer/cp_sat/encoder.py` (1,198) | CP-SAT constraint encoding: variable creation, domain encoding, constraint formulation. Encoding logic for different constraint types (adjacent, aligned, keepout, etc.) could be per-type modules. |
| `router_v6/adapter.py` (1,127) | Adapter between router_v6 and the deterministic pipeline. Converts between data formats, manages state translation, and provides fallback paths. Format conversion and orchestration are separate concerns. |
| `pcl/parser.py` (1,079) | PCL (Placement Constraint Language) parser. Lexer, grammar, AST construction, and semantic validation in one file. |

**Why this matters beyond aesthetics:**
- **Review latency**: A 1,500-line PR touching `loop.py` takes 3-5x longer to review than a 300-line PR touching a focused module. Reviewers skim rather than reason.
- **Test isolation**: Tests for `loop.py` must exercise constraint construction AND solver configuration AND solution extraction. A focused module lets tests target one concern.
- **Merge conflicts**: Monster files are changed in many PRs simultaneously. `loop.py` and `pipeline.py` are frequent conflict sources.
- **Cognitive load**: A new contributor opening `kicad_parser.py` faces 1,391 lines of recursive descent with no signposts for where board parsing ends and net parsing begins.

---

## Requirements

### Decomposition Principles

- **R1.** Decomposition is guided by class and function boundaries -- not arbitrary line-count targets. A file that naturally contains one large class with coherent methods stays as one file. A file that mixes unrelated concerns (e.g., parsing + serialization, or encoding + solution extraction) is split.
- **R2.** Each decomposed module has a single, documentable responsibility expressed in its module docstring. The docstring answers "what does this module do?" in one sentence.
- **R3.** Public API surface (what other modules import) does not change during decomposition. If `from temper_placer.placer.cp_sat.loop import CpsatLoop` works today, it works after decomposition via re-exports in the original module's location. The `.importlinter` contracts are updated to reflect the new internal structure without changing the public contract.

### Priority Targets

- **R4.** `placer/cp_sat/loop.py` (1,508 lines) is split into:
  - `loop.py` (~300 lines) -- orchestration: solver setup, stage dispatch, solution extraction
  - `_variable_manager.py` -- CP-SAT variable creation, domain management, lookup tables
  - `_constraint_builder.py` -- constraint formulation, gate translation, incremental building
  - `_solution_decoder.py` -- solution extraction, coordinate mapping, validation

- **R5.** `router_v6/astar_pathfinding.py` (1,452 lines) is split into:
  - `astar_pathfinding.py` (~400 lines) -- public A* search entry points
  - `_heuristics.py` -- cost function computation, distance estimates, congestion penalties
  - `_path_reconstruction.py` -- backtracking, waypoint extraction, smoothing

- **R6a.** `io/kicad_parser.py` (1,391 lines) is split by concern into: `kicad_parser.py` (public API) + `_parse_board.py`, `_parse_nets.py`, `_parse_zones.py`, `_parse_tracks.py`
- **R6b.** `io/kicad_writer.py` (1,311 lines) is split by concern into: `kicad_writer.py` (public API) + `_write_board.py`, `_write_nets.py`, `_write_zones.py`, `_write_tracks.py`

- **R7.** Remaining files (`pipeline.py`, `phased_component_assignment.py`, `clearance_grid.py`, `encoder.py`, `adapter.py`, `parser.py`) are decomposed according to the same principle (R1): split when unrelated concerns are mixed, keep whole when the abstraction is coherent.

### Test Coherence

- **R8.** Test files mirror the decomposed module structure. If `loop.py` splits into 4 modules, the corresponding test directory splits into 4 test files. Module-specific test files are created when the corresponding module exceeds 100 lines or has testable public behavior. Smaller modules may share test files. Existing test coverage is preserved; no test is deleted or weakened.
- **R9.** Tests that exercise cross-module behavior (integration-level tests) remain in-place and are updated to import from the public re-export location (R3).

### Non-Regression

- **R10.** The closure test (`tests/router_v6/ci_closure_test.py`), CP-SAT parity tests, and deterministic placement tests pass with equivalent results (DRC count within ±0, deterministic placement coordinates identical). If any variance is detected, it must be traceable to a non-deterministic source (e.g., CP-SAT heuristic tie-breaking) and documented.
- **R11.** A CI lint rule or test verifies that all public symbols from decomposed sub-modules are re-exported through the original import path. Missing re-exports are caught at CI, not at runtime.
- **R12.** Serialization round-trips (pickle, if used by the CP-SAT integration or pipeline state) are verified for any class whose `__module__` changes due to decomposition.
- **R13.** Import boundary enforcement (`.importlinter`) passes after decomposition. New internal modules that are implementation details are excluded from public-interface contracts.

---

## Acceptance Examples

- **AE1. Covers R4.** Given `loop.py` is decomposed, when `wc -l packages/temper-placer/src/temper_placer/placer/cp_sat/loop.py` runs, it reports <=400 lines (allows for inline docstrings and type annotations beyond the ~300 line functional estimate), and the original `CpsatLoop` class is still importable from `temper_placer.placer.cp_sat.loop`.
- **AE2. Covers R8.** Given `astar_pathfinding.py` splits into 3 modules, when `ls packages/temper-placer/tests/router_v6/` runs, it shows `test_astar_pathfinding.py`, `test_heuristics.py`, and `test_path_reconstruction.py` with preserved coverage levels.
- **AE3. Covers R10.** Given the closure test runs after all decompositions, it produces equivalent results: DRC violation count within ±0, deterministic placement coordinates identical. Any variance must be traceable to a non-deterministic source (e.g., CP-SAT heuristic tie-breaking) and documented.

---

## Success Criteria

- Zero files in `temper_placer/` exceed 1,000 lines, except where R1 would force an unnatural split; such exceptions require explicit justification in the decomposition PR (excluding `__init__.py` re-export hubs and generated code in `_constraint_types/`)
- Each of the 10 identified files, and any new module created by their decomposition, is under 1,000 lines (subject to the R1 exception for coherent abstractions)
- All public imports from decomposed modules remain valid (no import errors in dependent modules)
- Closure test, CP-SAT parity tests, and deterministic placement tests pass with identical results
- `.importlinter` violations count does not increase
- Test coverage percentage per decomposed module is >= pre-decomposition coverage for the original file
- No performance regression >5% on any existing benchmark for CP-SAT loop or A* pathfinding, or explicitly document that minor import-time and call overhead is accepted

---

## Scope Boundaries

- **In scope:** The 10 identified files exceeding 1,000 lines. Decomposition guided by class/function boundaries.
- **In scope:** Updating test file imports to match renamed modules and new import paths. Test logic and assertions must not change -- only import statements are updated.
- **In scope:** During decomposition PRs, only structural moves (and necessary import/name adjustments) are permitted. Bug fixes, renames, type annotation additions, and other enhancements are deferred to separate PRs unless required for tests to pass.
- **In scope:** New import-linter violations created by decomposition must be resolved within the decomposition PR. Pre-existing violations are not in scope to fix.
- **Out of scope:** Files under 1,000 lines are out of scope for this initiative but may be addressed in a follow-up if they violate R1 principles (mixed unrelated concerns).
- **Out of scope:** Router v6 consolidation (covered by `2026-07-01-systematic-dead-code-elimination-requirements.md`). This decomposition organizes the live code; dead-code elimination removes dead code.
- **Out of scope:** Circular dependency resolution (covered by separate brainstorm). Decomposition may incidentally simplify some cycles by creating cleaner boundaries, but cycle-breaking is not the goal.
- **Out of scope:** Performance optimization. Decomposition is structural only.
- **Out of scope (future phases):** If decomposition proves net-positive, a second phase targeting 800+ line files will be proposed as a separate brainstorm. This document does not authorize that work.

---

## Key Decisions

- **Re-export pattern over direct imports.** When a module splits, the original `__init__.py` or module file re-exports symbols from the new sub-modules so existing import paths continue working. Re-exports remain in place for at least 2 release cycles. Direct imports to new locations are encouraged in new code. Deprecation warnings are added before any removal. The removal PR is a separate, documented step with at least one release cycle of notice.
- **Underscore-prefix for internal modules.** New modules that are implementation details are named `_variable_manager.py`, not `variable_manager.py`. This signals to consumers and import-linter that these are not part of the public API.
- **No simultaneous dead-code removal.** Decomposition moves live code; dead code removal is a separate pass. Mixing the two makes it impossible to tell whether a test failure is from decomposition or deletion.

---

## Execution Plan

- **One PR per file.** Each monster file gets its own decomposition PR to keep reviews manageable. Risk is defined as: (a) test coverage gap (lower coverage = higher risk), (b) dependency fan-in (more dependents = higher risk), (c) change frequency in git history (more churn = higher risk). The least-to-most-risky ordering is: `io/kicad_writer.py`, `io/kicad_parser.py`, `pcl/parser.py`, `deterministic/stages/clearance_grid.py`, `deterministic/stages/phased_component_assignment.py`, `router_v6/pipeline.py`, `router_v6/adapter.py`, `router_v6/astar_pathfinding.py`, `placer/cp_sat/encoder.py`, `placer/cp_sat/loop.py`. This ordering is validated against per-file coverage data before implementation.

### Abort Criteria

- **Abort criteria:** If any decomposition PR (a) introduces >5 new import-linter violations that can't be resolved within the PR, (b) causes a test regression that requires >2 hours to diagnose, or (c) reduces per-module test coverage by >5%, pause the sequence and re-evaluate the approach.

---

## Dependencies / Assumptions

- **Methodology.** All decomposition follows TDD (Red-Green-Refactor per AGENTS.md). Each file split is validated by property-based tests (Hypothesis) proving that the decomposed modules' public API is indistinguishable from the original: for any input, the collection of decomposed modules produces the same output as the original monolithic file. Base cases (minimum inputs, boundary conditions) are proven correct; the PBT invariant generalizes to arbitrary inputs. No decomposition PR ships without at least one PBT invariant covering the split boundary.
- **Assumption:** The natural seam lines identified (class boundaries, public/private splits) are correct. If a file's internal coupling is tighter than estimated, decomposition may require a different split.
- **Dependency:** Depends on the existing test suite for regression safety. Test gaps in monster files mean decomposition risks are higher for those files.
- **Dependency:** Import boundary contracts in `.importlinter` and `import-linter-allowlist.yaml` must be updated atomically with each decomposition PR.
- **Dependency:** For new internal modules like `_variable_manager.py` imported by `loop.py`, add the module to the `implementation_detail` contract in `.importlinter`. Update `import-linter-allowlist.yaml` entries referencing decomposed modules.
- **Dependency:** Current per-file test coverage (source: `coverage.json`, date TBD): [table to be filled with coverage percentages for the 10 target files]. This data validates the least-to-most-risky PR sequencing.

---

## Outstanding Questions

### Resolve Before Planning

- **[Affects R4][User decision]** For `loop.py` specifically: the inline `@njit` Numba functions and OR-Tools CP-SAT calls share data structures. Is the seam between Numba-compiled grid operations and CP-SAT constraint construction clean enough to split, or does the performance coupling (shared ndarrays, in-place mutation) require keeping them together?
- **[Affects R4][Technical]** Before implementing R4 on loop.py: audit the Numba/OR-Tools data structure sharing. Produce a seam analysis showing which ndarrays and mutation sites cross proposed module boundaries. If coupling prevents the R4 split, the decomposition is revised.
- **[Affects R5][Technical]** The `astar_pathfinding.py` heuristics and path reconstruction share the same grid representation. Is the grid abstraction already factored out (into `astar_grid.py`) cleanly enough that heuristics and reconstruction can be separated without duplicating grid access logic?
- **[Affects R7][Technical]** For encoder.py decomposition: audit the `handlers/` subdirectory to determine the line-count split between `encoder.py` and its handlers. If encoder.py is pure dispatch (<600 lines of orchestration), remove it from the decomposition list.

### Deferred to Planning

- **[Affects R6][Technical]** KiCad S-expression format details: do board, net, zone, and track parsing share enough low-level helpers (atom readers, list walkers) that they belong in a shared `_sexpr_utils.py`, or is each domain's parsing self-contained?
- **[Affects R7][Technical]** For `encoder.py` (1,198 lines): what is the exact mapping of constraint types to encoding methods? The `handlers/` subdirectory already has per-constraint-type handlers -- does the encoder's bulk live in those handlers or in `encoder.py` itself?
