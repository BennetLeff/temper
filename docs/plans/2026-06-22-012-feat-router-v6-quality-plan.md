---
date: 2026-06-22
type: feat
origin: docs/ideation/2026-06-22-router-v6-quality-ideation.md
status: active
---

# Plan: Router V6 Completion Rate Improvements

## Problem Frame

Router V6 routes the Temper PCB with 0.5% completion. Five root causes identified in the ideation: SAT timeout too short, plane nets excluded from count, layer switching gated on THT, grid inflation, and no fallback for SAT-skipped nets. This plan applies the seven ranked fixes from the ideation, prioritized by effort-to-impact ratio.

## Implementation Units

### U1. Enable Theta* + Smoothing
**Goal:** Enable any-angle routing and path smoothing in the Router V6 adapter.
**Requirements:** Ideation idea #1
**Dependencies:** None
**Files:**
- Modify: `packages/temper-placer/src/temper_placer/router_v6/adapter.py`
**Approach:** Pass `enable_theta_star=True, enable_smoothing=True` to `RouterV6Pipeline()` constructor.
**Test scenarios:**
- Router V6 runs with theta* enabled, no crash, completion rate recorded
**Verification:** Closure test runs without errors, theta* and smoothing active in router output.

### U2. Count Plane Nets as Routed
**Goal:** Include plane nets (GND, VCC, PGND) in the success count since they're connected via copper pours.
**Requirements:** Ideation idea #2
**Dependencies:** None
**Files:**
- Modify: `packages/temper-placer/src/temper_placer/router_v6/routing_results.py`
- Modify: `packages/temper-placer/src/temper_placer/router_v6/routing_space.py` (plane net list)
**Approach:** After routing completes, count nets filtered by `should_route()` as success. Extract the plane net list from the existing filter logic.
**Test scenarios:**
- Board with GND, VCC, PGND nets: completion_rate includes them as successes
- Board with no plane nets: completion unchanged
**Verification:** Completion rate increases from 0.5% to >10% on temper_placed.

### U3. Increase SAT Timeout
**Goal:** Give the SAT topology solver enough time to assign channel paths to all nets.
**Requirements:** Ideation idea #3
**Dependencies:** None
**Files:**
- Modify: `packages/temper-placer/src/temper_placer/router_v6/pipeline.py`
**Approach:** Change the hardcoded SAT timeout from 5s to 30s. Locate the timeout value in the SAT solver invocation.
**Test scenarios:**
- SAT solver runs with 30s timeout, more nets get channel assignments
**Verification:** Stage 3 output shows more nets with channel assignments. Stage 4 A* routes more nets.

### U4. Structural Fixes (Layer Switching + Fallback + Rip-Up + Inflation)
**Goal:** Apply the remaining four fixes for deeper routing quality improvement.
**Requirements:** Ideation ideas #4, #5, #6, #7
**Dependencies:** U1, U2, U3
**Files:**
- Modify: `packages/temper-placer/src/temper_placer/router_v6/astar_pathfinding.py` — rip-up depth + layer switch + fallback
- Modify: `packages/temper-placer/src/temper_placer/router_v6/pipeline.py` — grid inflation
**Approach:**
- (a) Rip-up depth: change hardcoded 15→30, 30→60
- (b) Layer switching: remove THT-gating condition, allow via insertion at any free grid cell on adjacent layer
- (c) Fallback route: nets without SAT channel assignment get a direct A* attempt between endpoints
- (d) Grid inflation: near pads, use `trace_width/2` only (skip clearance term); KiCad DRC enforces clearance post-route
**Test scenarios:**
- Layer switch: SMD-only test board routes across layers
- Fallback: nets skipped by SAT still attempt A* and appear in completion count
- Rip-up: dense board completes with fewer failures
- Grid inflation: DRC check after routing shows no clearance violations beyond baseline
**Verification:** Closure test completion rate increases. No crashes in any router stage.

## Risks

- **Theta* may be slower**: any-angle pathfinding expands more neighbors per node. Accept as trade-off for higher completion.
- **SAT 30s timeout**: increases wall-clock time from ~200s to potentially ~250s. Acceptable for a CI gate.
- **Layer switching without THT**: blind/buried vias may violate fabrication rules if placed incorrectly. KiCad DRC catches these.
- **Grid inflation change**: clearance relaxations could produce DRC violations. KiCad DRC is the backstop.

## Test Strategy

- Existing tests in `tests/regression/` run unchanged — no new test files needed
- Closure test is the integration gate: run against `pcb/temper_placed.kicad_pcb`
- Acceptance: completion rate >10% (up from 0.5%), DRC errors do not increase
