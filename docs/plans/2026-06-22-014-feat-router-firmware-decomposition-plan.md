---
title: "feat: Decompose Router God-Objects and Firmware State Machine (N6 U5-U8)"
type: feat
status: active
date: 2026-06-22
origin: docs/plans/2026-06-22-006-feat-cli-zoning-loc-cap-plan.md
---

# feat: Decompose Router God-Objects and Firmware State Machine

## Summary

Extracts the four remaining decomposition targets from the N6 LOC cap plan: three router god-objects (`exact_geometry_router.py` 3811 lines, `astar_pathfinding.py` 2289 lines, `sequential_routing.py` 2046 lines) and the firmware state machine (`state_machine.c` 1035 lines). Each file is split along the seams identified in the parent plan's Key Technical Decisions. The LOC cap gate (`.loc-allowlist.txt` + `tools/loc_cap_check.py`) enforces the 1000-line ceiling. Public import paths are preserved via `__init__.py` re-exports so no callers break. The three router decompositions ship as separate PRs (one per file, descending risk); the firmware decomposition ships as a fourth.

---

## Problem Frame

Four source files exceed the 1000-line cap enforced by the N6 LOC gate. They are allowlisted under the baseline but must decompose to under-cap modules for the allowlist to shrink:

| File | Lines | Primary obstacle |
|------|-------|-----------------|
| `exact_geometry_router.py` | ~3811 | Single class with path-construction, grid/obstacle, scoring, and orchestration methods all in one file |
| `astar_pathfinding.py` | ~2289 | Free functions for net routing, grid helpers, lane detection, pathfinding, and diagnostics |
| `sequential_routing.py` | ~2046 | Single `SequentialRoutingStage` class + one dataclass; methods are tightly coupled to `self` state |
| `state_machine.c` | ~1035 | 8 states × (entry + update) = 16 handler functions in same file as orchestration shell |

The CLI decomposition (Phase 2 of N6) already proved the pattern: extract served modules (subcommands) and servant modules (IO, args, signal), re-export from `__init__.py`, and let the LOC gate shrink the allowlist entry.

---

## Scope Boundaries

### In scope

- R1: Decompose `exact_geometry_router.py` into `exact_geometry_router.py` (orchestration, <1000 lines) + `exact_geometry_router_internals.py` (path construction, grid/obstacle, scoring, <3000 lines)
- R2: Decompose `astar_pathfinding.py` into `astar_pathfinding.py` (orchestration) + `astar_helpers.py` + `astar_grid.py` + `astar_lanes.py` (each <1000 lines)
- R3: Decompose `sequential_routing.py` into `sequential_routing.py` (orchestration) + `sequential_routing_dataclasses.py` + `sequential_routing_helpers.py`
- R4: Decompose `state_machine.c` into `state_machine.c` (orchestration) + `state_handlers.c` + `state_handlers.h`
- R5: Each decomposition preserves public import paths via `__init__.py` re-exports
- R6: LOC gate passes with decomposed files removed from `.loc-allowlist.txt`
- R7: All existing tests pass unchanged (no test changes except import path updates)

### Deferred

- Decomposing the 10 additional >1000-line `.py` files (kicad_parser.py, kicad_writer.py, etc.) — N7 candidate
- Branch-coverage improvements in the decomposed files
- `SequentialRoutingStage` method-level refactoring beyond the stateless-method extraction

### Out of scope

- Changing router algorithm behavior
- Adding new features to decomposed modules
- Decomposing firmware beyond `state_machine.c`

---

## Key Technical Decisions

### Router decomposition principle: extract, don't rewrite

Each decomposition extracts cohesive groups of symbols (classes, functions, constants) into named submodules and re-exports them from the parent package's `__init__.py`. No public symbol is renamed or reorganized beyond the file-level split. This minimizes diff size and review surface.

### `exact_geometry_router.py` seam (U1)

From the parent plan's seam analysis, visible method groups:
- **Grid/obstacle setup**: methods building occupancy grids, inflating obstacles, computing net-aware cost surfaces
- **Path construction**: methods computing exact-geometry paths (non-grid, using Shapely geometry operations)
- **Scoring/heuristics**: methods computing cost estimates, ranking candidate paths
- **Orchestration**: `route()` entry point, stage setup, result assembly

Extract grid/obstacle + path-construction + scoring into `exact_geometry_router_internals.py`. The orchestration stays in `exact_geometry_router.py`. Public import path: `from temper_placer.router_v6 import ExactGeometryRouter` continues to work via `router_v6/__init__.py` re-export.

### `astar_pathfinding.py` seam (U2)

From the parent plan's seam analysis, visible function groups:
- **Net routing**: `run_astar_pathfinding()`, `_route_single_net_2d()`, routing orchestration → stays in `astar_pathfinding.py`
- **Grid helpers**: `_find_access_node()`, `_is_free()`, occupancy checks → `astar_grid.py`
- **Pathfinding algo**: `_astar_search()`, `_astar_search_theta_star()`, neighbor expansion → `astar_core.py`
- **Lane detection**: `_extract_lanes()`, `_build_lane_graph()` → `astar_lanes.py`
- **Diagnostics**: `_record_failure()`, `_print_timing()` → `astar_diagnostics.py`

The orchestration function `run_astar_pathfinding()` stays; all helpers move. Public import: `from temper_placer.router_v6 import run_astar_pathfinding`.

### `sequential_routing.py` seam (U3)

From parent plan seam analysis:
- `DiffPairConfig` (dataclass) → `sequential_routing_dataclasses.py`
- Private methods of `SequentialRoutingStage` that do NOT touch `self` state (identified by static analysis) → `sequential_routing_helpers.py`
- `SequentialRoutingStage` orchestration + `COUPLED_ROUTER_AVAILABLE` flag → stays in `sequential_routing.py`

### `state_machine.c` seam (U4)

From parent plan decision:
- 16 per-state handler functions (`state_init_*`, `state_idle_*`, etc.) → `firmware/main/state_handlers.c`
- Handler declarations → `firmware/main/state_handlers.h`
- Orchestration shell (`state_machine_init`, `state_machine_update`, `transition_to`, etc.), static state struct, setters → stays in `state_machine.c`
- Both `.c` files added to `SRCS` in `firmware/main/CMakeLists.txt`

---

## Implementation Units

### U1. Decompose `exact_geometry_router.py` (PR 1)

**Goal:** Split ~3811-line file into orchestration (<1000) + internals (<3000).

**Files:**
- Create: `packages/temper-placer/src/temper_placer/router_v6/exact_geometry_router_internals.py`
- Modify: `packages/temper-placer/src/temper_placer/router_v6/exact_geometry_router.py`
- Modify: `packages/temper-placer/src/temper_placer/router_v6/__init__.py`

**Approach:**
1. Scan `exact_geometry_router.py` for method groups. Move grid/obstacle, path-construction, and scoring methods into `exact_geometry_router_internals.py`.
2. In `exact_geometry_router.py`, import the extracted methods from the internals module.
3. `__init__.py` already re-exports `ExactGeometryRouter` — verify no change needed.
4. Remove `exact_geometry_router.py` from `.loc-allowlist.txt`.
5. Add `exact_geometry_router_internals.py` to `.loc-allowlist.txt` with ticket reference.

**Verification:**
- `uv run python tools/loc_cap_check.py` passes with updated allowlist.
- Existing router tests pass.
- `from temper_placer.router_v6 import ExactGeometryRouter` works.

---

### U2. Decompose `astar_pathfinding.py` (PR 2)

**Goal:** Split ~2289-line file into astar_pathfinding.py (<1000) + helpers.

**Files:**
- Create: `packages/temper-placer/src/temper_placer/router_v6/astar_grid.py`
- Create: `packages/temper-placer/src/temper_placer/router_v6/astar_core.py`
- Create: `packages/temper-placer/src/temper_placer/router_v6/astar_lanes.py`
- Create: `packages/temper-placer/src/temper_placer/router_v6/astar_diagnostics.py`
- Modify: `packages/temper-placer/src/temper_placer/router_v6/astar_pathfinding.py`
- Modify: `packages/temper-placer/src/temper_placer/router_v6/__init__.py`

**Approach:**
1. Extract grid helpers (`_find_access_node`, `_is_free`, bounds checking) → `astar_grid.py`.
2. Extract A* algo (`_astar_search`, `_astar_search_theta_star`, neighbor expansion) → `astar_core.py`.
3. Extract lane detection (`_extract_lanes`, `_build_lane_graph`) → `astar_lanes.py`.
4. Extract diagnostics (`_record_failure`, timing) → `astar_diagnostics.py`.
5. `run_astar_pathfinding()` imports from all helper modules.
6. Remove `astar_pathfinding.py` from `.loc-allowlist.txt`.
7. Add each new >1000-line module to allowlist; if all <1000, no new entries needed.

**Verification:**
- LOC gate passes.
- A* perf regression test (`test_astar_perf_regression.py`) unchanged.
- All router tests pass.

---

### U3. Decompose `sequential_routing.py` (PR 3)

**Goal:** Split ~2046-line file into orchestration (<1000) + helpers.

**Files:**
- Create: `packages/temper-placer/src/temper_placer/deterministic/stages/sequential_routing_dataclasses.py`
- Create: `packages/temper-placer/src/temper_placer/deterministic/stages/sequential_routing_helpers.py`
- Modify: `packages/temper-placer/src/temper_placer/deterministic/stages/sequential_routing.py`
- Modify: `packages/temper-placer/src/temper_placer/deterministic/stages/__init__.py`

**Approach:**
1. Extract `DiffPairConfig` dataclass → `sequential_routing_dataclasses.py`.
2. Scan `SequentialRoutingStage` methods for stateless helpers (no `self` mutation). Extract → `sequential_routing_helpers.py`. Implementer identifies these with a grep for `def _` methods that only read `self` attributes without assigning. If none are pure stateless helpers, accept the mixin fallback (parent plan Risk Analysis row 4).
3. `__init__.py` re-exports `SequentialRoutingStage` and `DiffPairConfig` from new locations.
4. Remove `sequential_routing.py` from allowlist; add new modules if needed.

**Verification:**
- LOC gate passes.
- Deterministic placement pipeline unchanged.
- `from temper_placer.deterministic.stages import SequentialRoutingStage` works.

---

### U4. Decompose `firmware/main/state_machine.c` (PR 4)

**Goal:** Split 1035-line file into orchestration (<1000) + state handlers.

**Files:**
- Create: `firmware/main/state_handlers.c`
- Create: `firmware/main/state_handlers.h`
- Modify: `firmware/main/state_machine.c`
- Modify: `firmware/main/CMakeLists.txt`

**Approach:**
1. Extract 16 per-state handler functions into `state_handlers.c`. Each handler is a pair: `state_<name>_entry(void)` and `state_<name>_update(void)`.
2. Declare all 16 handlers in `state_handlers.h`.
3. `state_machine.c` includes `state_handlers.h` and retains: the static state struct (lines ~50-93), `state_machine_init`, `state_machine_update`, `transition_to`, `check_safety_interlocks`, `fault_cleared`, `show_message_then_transition`, `run_self_test`, setters.
4. Add `state_handlers.c` to `SRCS` in `firmware/main/CMakeLists.txt`.
5. Remove `state_machine.c` from `.loc-allowlist.txt`. Add `state_handlers.c` only if >1000 lines (expected ~600 — no addition needed).

**Verification:**
- `cmake -B firmware/test/build firmware/test && cmake --build firmware/test/build` succeeds.
- `./firmware/test/build/test_state_machine_only` — all 49 tests pass.
- LOC gate passes with `state_machine.c` removed from allowlist.

---

## System-Wide Impact

- **Router V6**: internal module structure changes; public API unchanged.
- **Firmware**: two `.c` files instead of one; build system updated. No behavioral change.
- **`.loc-allowlist.txt`**: ~15 entries reduced by 4 (the four god-object entries removed, new sub-module entries added only if they exceed 1000 lines).
- **Test suite**: no test changes required (tests import via public API, not internal module paths).

---

## Risk Analysis & Mitigation

| Risk | Severity | Likelihood | Mitigation |
|------|----------|------------|------------|
| Method extraction breaks tight coupling in `ExactGeometryRouter` | Medium | Medium | Use mixin pattern if extraction proves too coupled. The class stays intact; internals are imported via mixin base class. |
| `SequentialRoutingStage` has no stateless helpers — U3 produces no extraction | Low | Medium | Parent plan's Risk Analysis row 4: mixin fallback is acceptable. If no helpers, U3 is a no-op and `sequential_routing.py` stays on allowlist. |
| `astar_pathfinding.py` function-scoped imports of `AdaptiveGrid` break when moved | Medium | Low | Verify all imports resolve after extraction. Function-scoped imports are intra-module; they stay in `astar_pathfinding.py`. |
| Firmware build breaks due to include path resolution | Low | Low | Both `.c` files are in `firmware/main/` — same directory, no include path change needed. |
| Cross-file `static` declarations in `state_machine.c` prevent extraction | Medium | Low | The static state struct stays in `state_machine.c`. Handlers access it via the existing `sm_ctx` pointer passed by the update loop. No `static` variable migration needed. |

---

## Test Strategy

- **U1-U3 (router decompositions):** Existing router tests in `packages/temper-placer/tests/router_v6/` serve as the regression gate. No new tests needed — decomposition is structural, not behavioral.
- **U4 (firmware):** `test_state_machine_only` (49 tests) serves as the regression gate. Firmware CI job rebuilds from clean.
- **LOC gate:** `uv run python tools/loc_cap_check.py` verifies each PR reduces the allowlist by removing the decomposed god-object entry.
