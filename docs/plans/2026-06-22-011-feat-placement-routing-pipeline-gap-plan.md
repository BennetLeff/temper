---
date: 2026-06-22
type: feat
origin: docs/brainstorms/2026-06-22-placement-routing-pipeline-gap-requirements.md
status: active
---

# Plan: Placement-to-Routing Pipeline Gap

## Problem Frame

The closure test at `packages/temper-placer/src/temper_placer/regression/closure_test.py` runs parse → place → route → DRC but both placement and routing steps fail as `ImportError` — the pipeline reports PASS with zero real results. Router V6 has a fully implemented 4-stage pipeline (`RouterV6Pipeline.run(pcb_path)`) but no closure-test-compatible entry point. The deterministic placer (`place_power_stage_template`) exists but has no `benders_placement` wrapper. This plan writes the two adapter modules that make both steps produce real results.

## Requirements Trace

| Requirement | Source |
|-------------|--------|
| `benders_placement(parsed, seed, *, strategy)` — placement module with strategy pattern | R1 |
| `route_pcb(parsed, placements, seed)` — Router V6 adapter | R2 |
| Closure test produces non-zero placement/routing results, no import warnings | R3, SC1 |
| Graceful degradation when strategy not available | R3 (AE3) |
| Closure test verification passes (AE1: non-zero iterations/completion, AE2: no import warnings, AE3: graceful degradation) | R4 |
| Strategy pattern is forward-compatible; adding `strategy="benders"` requires no closure test or route_pcb changes | SC2 |
| No changes to RouterV6Pipeline internals | K2 |

## Ground truth interfaces (verified against working tree)

| Symbol | Actual location | Key fields |
|--------|----------------|------------|
| `place_power_stage_template(netlist, board, template, zone_name, initial_positions)` → `PlacementResult` | `temper_placer.placer.deterministic` | `.positions` (N,2 ndarray), `.rotations` (N,), `.placed_refs` (list), `.unplaced_refs` (list) |
| `RouterV6Pipeline.run(pcb_path: Path)` → `RouterV6Result` | `temper_placer.router_v6.pipeline` | `.completion_rate` (property), `.success_count` (property), `.escape_vias`, `.stage2-4` |
| `ClosureTest(pcb_path, seed)` → `.run()` → `ClosureResult` | `temper_placer.regression.closure_test` | `.benders_iterations` (int), `.router_completion_pct` (float) |
| `parse_kicad_pcb_v6(pcb_path)` → `ParsedPCB` | `temper_placer.io.kicad_parser` | Used as input to both placement and routing |

## Implementation Units

### U1. Placement module (`benders_loop`)

**Goal:** Expose `benders_placement(parsed, seed, *, strategy)` that delegates to the existing deterministic placer and returns the closure-test-compatible result shape.

**Requirements:** R1

**Files:**
- Create: `packages/temper-placer/src/temper_placer/placement/__init__.py`
- Create: `packages/temper-placer/src/temper_placer/placement/benders_loop.py`
- Create: `packages/temper-placer/tests/placement/__init__.py`
- Create: `packages/temper-placer/tests/placement/test_benders_loop.py`

**Approach:** Write a `benders_placement` function that:
1. Extracts `netlist` and `board` objects from `parsed` (the `ParsedPCB` from `parse_kicad_pcb_v6`)
2. Loads the template from `temper_placer.placer.template` (default: HalfBridgeTemplate)
3. Calls `place_power_stage_template(netlist, board, template)` from `temper_placer.placer.deterministic`
4. Converts `PlacementResult` to the dict shape `{ref: (x, y)}` the closure test expects
5. Returns a `BendersPlacementResult` dataclass with `.placements: dict[str, tuple]`, `.iterations: int` (1 for template), `.cuts: int` (0 for template)
6. Strategy pattern: `strategy` kwarg selects the placement function. Default `"template"`. Unknown strategy name logs warning and returns empty placements (AE3). Benders hooks into this slot later by registering under `strategy="benders"`.

**Error handling:** If parsed data is invalid (missing netlist or board), raise `ValueError` with a descriptive message — the closure test catches exceptions and records them as errors. If the placer throws, propagate the exception so the closure test records a failure rather than silently returning zero placements.

**Patterns to follow:** `ClosureResult` dataclass style in `closure_test.py`; `import ... except ImportError` fallback pattern in `closure_test.py:84-103`

**Test scenarios:**
- Happy path: `benders_placement(parsed, 42)` on a valid PCB returns `BendersPlacementResult` with non-empty `.placements`
- Default strategy: `strategy="template"` (or no strategy arg) invokes deterministic placer
- Unknown strategy: `strategy="benders"` returns empty placements with a warning logged, does not raise
- Transform: placement dict keys match `.placed_refs` from the underlying `PlacementResult`, values are (x, y) tuples
- Import safety: module is importable without importing Router V6 or JAX

**Verification:** `python3 -c "from temper_placer.placement.benders_loop import benders_placement; print(type(benders_placement))"` shows a callable. On a valid PCB, returns a result with `.placements`, `.iterations`, `.cuts`.

---

### U2. Router V6 adapter (`route_pcb`)

**Goal:** Export a `route_pcb(parsed, placements, seed)` function that feeds placement data into Router V6 and returns a routing result the closure test can read.

**Requirements:** R2

**Dependencies:** U1 (needs the placement dict format)

**Files:**
- Modify: `packages/temper-placer/src/temper_placer/router_v6/__init__.py`
- Create: `packages/temper-placer/src/temper_placer/router_v6/adapter.py`
- Create: `packages/temper-placer/tests/router_v6/test_adapter.py`

**Approach:** Write an `adapter.py` module with:
1. `route_pcb(parsed, placements, seed)` function that:
   - Confirmed: `RouterV6Pipeline.run()` accepts only `pcb_path: Path` (file-path-only, verified from `pipeline.py:143`). The adapter writes the placement-modified board to a temp `.kicad_pcb` file in `tempfile.gettempdir()`, invokes the pipeline, then removes the temp file.
   - Calls `RouterV6Pipeline(repo_root=..., seed=seed).run(temp_pcb_path)` to invoke the 4-stage routing pipeline
   - Returns a `RoutingResult` dataclass with `.completion_rate` (float from `RouterV6Result.completion_rate`)
2. Export `route_pcb` from `temper_placer.router_v6.__init__`

**Patterns to follow:** `RouterV6Pipeline.__init__` and `.run` signatures from `pipeline.py:113-143`; `ClosureTest` import-and-try pattern

**Error handling:** If Router V6 pipeline fails, propagate the exception — the closure test records it as an error. If `placements` is empty or None, log a warning and pass through to the router without modifying positions (the board's existing positions are used). Temp file cleanup in a `finally` block so failures don't leak files.

**Test scenarios:**
- Happy path: `route_pcb(parsed, placements, 42)` on a valid board returns `RoutingResult` with non-zero `.completion_rate`
- No placements: calling with empty `placements = {}` does not crash — Router V6 runs with whatever positions the board already has
- Import safety: adapter is importable without requiring JAX

**Verification:** `python3 -c "from temper_placer.router_v6 import route_pcb"` succeeds. Integration: closure test prints `Router completion: N.N%` with N > 0.

---

### U3. Integration verification

**Goal:** Confirm the full pipeline produces real results per SC1 and R3.

**Requirements:** R3, R4, SC1, SC2

**Dependencies:** U1, U2

**Files:**
- Read: `packages/temper-placer/tests/regression/test_closure.py` (existing, verify unchanged)

**Approach:**
1. Run the closure test against `placement_optimized.kicad_pcb`: `ClosureTest(pcb_path=Path("placement_optimized.kicad_pcb"), seed={"benders_seed": 42, "router_seed": 42}).run()`
2. Assert: `result.benders_iterations > 0` (real placement ran)
3. Assert: `result.router_completion_pct > 0.0` (real routing ran)
4. Assert: No import warnings in `result.warnings` for Benders or Router
5. Run existing `tests/regression/test_closure.py` — all pass

**Verification:** Closure test output shows non-zero placement and routing numbers, no ImportError warnings. Existing regression tests unchanged.

---

## Scope Boundaries

### Deferred to Follow-Up Work
- Implementing Benders decomposition algorithm (strategy slot is reserved, not filled)
- Improving placement quality of the deterministic placer
- Router V6 performance tuning or stage-level configuration

## Risks

- **Router V6 may not accept external placements.** If `RouterV6Pipeline.run()` uses positions from the PCB file and can't be influenced by external data, the adapter must write a temp `.kicad_pcb` file with modified positions. This is a file-format dependency — verify during U2 implementation.
- **Existing placer may not cover all component types.** `place_power_stage_template` is designed for power-stage components. Non-power components on the board may remain unplaced, producing `unplaced_refs`. The closure test should handle partial placement gracefully (the DRC step will flag missing components).
- **Strategy pattern abstraction overhead.** A strategy pattern with one implementation is premature abstraction. If Benders is never built, the strategy kwarg is dead weight. Accept this risk — the ideation plan explicitly committed to Benders, so the slot has a known consumer.

## Test Strategy

- U1 unit tests: verify placement dict shape, strategy selection, graceful degradation
- U2 unit tests: verify `route_pcb` returns `RoutingResult` with real completion rate
- U3 integration: run closure test end-to-end, assert real numbers
- Existing tests in `tests/regression/test_closure.py` serve as the regression gate
