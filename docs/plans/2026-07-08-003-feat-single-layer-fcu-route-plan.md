---
title: "feat: Single-layer F.Cu routing gate — prove the router routes at all"
type: feat
status: draft
date: 2026-07-08
origin: docs/brainstorms/2026-07-08-single-layer-route-requirements.md
---

# feat: Single-Layer F.Cu Route — Router Completion Gate

## Summary

Route 100% of nets on the placed temper board on a single layer (F.Cu). Implement a `RoutingGate` conforming to the shared gate contract (`GateResult{status: CLEAN|VIOLATIONS|UNMEASURED}`), extend `test_regression_drc.py` to assert `unconnected_items=0` AND `total_errors=0` on the routed board, and wire the routing gate into CI.

---

## Problem Frame

The router (`router_v6`) has never been proven to route the temper board end-to-end on this machine. The golden-board DRC gate (`test_golden_board_drc_regression` in `test_regression_drc.py`) currently measures placement-only DRC. Before adding stackup, physics constraints, or 45° routing, the router must demonstrate it can route every net on the simplest possible configuration — a single signal layer.

The temper board has 24 nets. The `PlaceRouteLoop.run()` method already invokes `route_pcb()` in its round-trip. The gap is: no gate verifies that the routed board passes KiCad DRC with zero unconnected items and zero total errors.

(see origin: `docs/brainstorms/2026-07-08-single-layer-route-requirements.md`)

---

## Requirements

- **R1 (100% routing).** `PlaceRouteLoop.run()` completes with `unconnected_items = 0` in `kicad-cli pcb drc` output on the routed `.kicad_pcb`. Every net in the netlist must be routed. The loop already accumulates `completion_rate`; this gate is the ground-truth measurement against KiCad DRC.
- **R1a (completion_rate internal signal).** The existing `RoutingResult.completion_rate` must read 1.0. If the internal router reports 1.0 but KiCad DRC reports `unconnected_items > 0`, the signal-to-ground gap is a router-completion-measurement bug — the DRC truth gate wins.
- **R2 (zero DRC errors on routed board).** `kicad-cli pcb drc` returns 0 total errors on the routed output PCB. This includes track-to-track clearance, track-to-pad clearance, and any routing-introduced violations.
- **R3 (golden-board gate extended to routing).** `test_regression_drc.py` gains a `test_golden_board_routing_drc_regression` that runs `solve_placement → route_pcb → kicad-cli pcb drc` and asserts `unconnected_items = 0` AND `total_errors = 0`.
- **R3a (routing delta decomposition).** The test decomposes routing-only DRC errors: `routing_introduced = routed_errors - placement_errors`. This isolates routing bugs from placement bugs and catches regressions in either subsystem independently.
- **R4 (RoutingGate per gate contract).** Implement `RoutingGate` conforming to `docs/brainstorms/2026-07-08-gate-contract.md`:
  - `stage = GateStage.ROUTING`
  - `name = "routing_drc"`
  - `check(state: BoardState) -> GateResult` returns `CLEAN` when KiCad DRC reports zero violations of all types; `VIOLATIONS` when violations exist; `UNMEASURED` when kicad-cli exits nonzero or the routed PCB path is missing.
  - `to_delta(violation) -> ConstraintDelta | None`: map unconnected items to `SeparatedConstraint` deltas on involved component pairs; return `None` for clearance violations whose components are intra-component (placement-irreducible).
- **R5 (placement dependency).** Must use the existing CP-SAT courtyard+edge placement from plan `2026-07-08-001`, units U1-U6. Placement-relevant DRC must be ≤ the U6 target before routing begins.
- **R6 (F.Cu single-layer only).** Route on F.Cu signal layer only. Multi-layer routing (B.Cu, vias) is out of scope for W1.

**Origin actors:** `PlaceRouteLoop`, `RoutingGate`, KiCad CLI DRC
**Origin flows:** place → route → DRC measure → gate check → CI assert
**Origin acceptance examples:** `test_golden_board_routing_drc_regression` passes in CI

---

## Scope Boundaries

- Multi-layer routing (B.Cu, vias, stackup configuration) — out of scope (W2).
- Physics-constrained routing (commutation loops, thermal anchoring) — out of scope (W3).
- 45° routing, via optimization, aesthetic track layout — out of scope (W4).
- W5 compound gate loop orchestration — out of scope (gates register but the full loop is W5).
- Modifying router_v6's core pathfinding algorithm — out of scope. Changes to router_v6 should be parameter tuning, net-ordering adjustments, or bug fixes, not algorithmic rewrites.
- Replacing the existing `validation/validation_gates.py` system — out of scope. The new `RoutingGate` is the contract-conformant gate for the place→route loop; the existing `ValidationGate` hierarchy serves the production-readiness workflow and is not modified by W1.

---

## Context & Research

### Relevant Code and Patterns

- `packages/temper-placer/src/temper_placer/placer/cp_sat/loop.py:87` — `PlaceRouteLoop` class. Already calls `route_pcb()` in `_route_placement()` (line 213) and tracks `completion_rate`. The `routed_pcb_content` field on `RoutingResult` (adapter.py:99) carries the full routed PCB text for DRC measurement.
- `packages/temper-placer/src/temper_placer/router_v6/adapter.py:373` — `route_pcb()` function. Writes a placed PCB, invokes `RouterV6Pipeline.run()`, returns `RoutingResult` with `completion_rate`, `unrouted_nets`, `drc_violations`, and `routed_pcb_content`. The router runs single-layer by default (only F.Cu pads are present in the minimal PCB).
- `packages/temper-placer/tests/placer/cp_sat/test_regression_drc.py:100` — `test_golden_board_drc_regression`. Placement-only DRC gate: parses `kicad-cli pcb drc --format json` output, counts violations by type, distinguishes placement-fixable from placement-irreducible. The routing gate reuses the same DRC parsing pattern.
- `packages/temper-placer/src/temper_placer/validation/drc.py:53` — `DRCViolationType.UNCONNECTED_ITEMS = "unconnected_items"`. The DRC type enum already includes the key measurement for the routing gate.
- `packages/temper-placer/src/temper_placer/regression/drc_ratchet.py` — `DrcRatchet` class. Existing CI pipeline that checks DRC ceilings on boards. The routing gate extends this pattern by introducing a routed-board ceiling.
- `docs/brainstorms/2026-07-08-gate-contract.md` — Shared gate contract defining `Gate`, `GateResult{status: CLEAN|VIOLATIONS|UNMEASURED}`, `GateStage{PLACEMENT|ROUTING}`, `Violation`, and `BoardState`. The `RoutingGate` is the first `ROUTING`-stage gate.

### Institutional Learnings

- **router-v6-closure-rate-100pct-2026-06-24**: `max_iter=500_000` is the path-quality sweet spot on temper.kicad_pcb. The kernel default of 1M explores further but lands SPI_MOSI on a different tie-break path and the reroute loop can't recover it (95.83% vs 100.0% at 500k). Parameter tuning must reference this documented sweet-spot table.
- **cp-sat-constraint-encoder-greenfield-hard-ceiling-2026-07-05**: Every handler must wire its constraint to `OnlyEnforceIf(assumption)` for UNSAT-core extraction. The RoutingGate maps unconnected nets to per-pair SEPARATED deltas — the same constraint encoding pipeline the model already supports.
- **two-tier-acceptance-gate-unsat-surfacing-2026-07-05**: Handle `UNKNOWN` solver status correctly. The gate contract's `UNMEASURED` status serves the same role for routing: distinguish "measured, clean" from "couldn't measure."
- **PlaceRouteLoop `_route_placement()` pattern**: The loop already writes a temporary PCB, calls `route_pcb()`, and returns a `RoutingResult` with `routed_pcb_content`. The routing gate reuses this result — no need to re-route a second time. The gate writes the routed content back to a temp file for kicad-cli DRC.
- **test_refactors_gating_pipeline.py absence**: `test_regression_drc.py` is the canonical golden-board test file. The routing gate test goes here (new test function), not in a separate file — same board, same DRC harness, different pipeline stage.

### External References

- `kicad-cli pcb drc --format json` — produces `{violations: [...]}` with per-violation `type` and `description` fields. `unconnected_items` is a top-level array in the JSON output.
- `RouterV6Pipeline` defaults: `enable_theta_star=False`, `enable_lazy_theta_star=False`, `enable_smoothing=False`, `max_iter=500_000`. All three advanced features are disabled for the smoke-equivalent path.

---

## Key Technical Decisions

- **RoutingGate writes routed_pcb_content to temp file for kicad-cli.** The `RoutingResult.routed_pcb_content` field (adapter.py:99) carries the full routed PCB text. The gate writes this to a temporary `.kicad_pcb` file, runs `kicad-cli pcb drc`, and parses the JSON output. This avoids needing the loop to track file paths — the gate is self-contained.
- **DRC truth gate wins over internal completion_rate.** If `completion_rate == 1.0` but `kicad-cli pcb drc` reports `unconnected_items > 0`, the gate returns `VIOLATIONS`. The internal completion metric is a signal; the ground truth is the DRC measurement. This is the same two-tier discipline as the current `AcceptanceGate` (gate.py).
- **Separate routing-introduced violations from placement-inherited.** The test computes `routing_delta = routed_violations - placement_violations` by type, using the placement-only DRC as baseline. This isolates regressions: a track-to-track clearance violation at 0.15mm is a routing bug; a shorting_items violation that existed at placement is a placement bug. The gate asserts total=0, but the delta decomposition identifies which subsystem needs attention.
- **Gate contract implementation: new file in `placer/cp_sat/`.** `RoutingGate` goes in a new file `packages/temper-placer/src/temper_placer/placer/cp_sat/gates.py` alongside the contract types. This co-locates all place→route loop gate implementations. The existing `validation/validation_gates.py` serves the production-readiness workflow and is not modified.
- **Contract types live in a shared module.** The `Gate`, `GateResult`, `GateStatus`, `GateStage`, `Violation`, `ViolationType`, `BoardState`, and `ConstraintDelta` type aliases from the gate contract go in `packages/temper-placer/src/temper_placer/placer/cp_sat/gate_contract.py`. This single module is the SSOT for the contract — all gates (DrcGate, RoutingGate, PhysicsGate, QualityGate) import from it.
- **Router fix scope: parameter tuning, not algorithm changes.** If the router cannot achieve 100% completion on F.Cu, the fix path is: (a) verify max_iter sweet spot (500k), (b) adjust net-ordering heuristics, (c) fix net-resolution bugs in the Numba A* kernel. Algorithmic rewrites (theta-star, smoothing) are out of scope for W1.
- **BoardState is the gate input, not run-time orchestration.** The gate contract defines `BoardState` as a frozen snapshot. For W1, the `RoutingGate.check()` receives a `BoardState` populated from the `PlaceRouteLoop` result — it does not orchestrate the loop. The W5 compound loop owns orchestration.

---

## Open Questions

### Resolved During Planning

- **Where does the gate contract module live?** `packages/temper-placer/src/temper_placer/placer/cp_sat/gate_contract.py` — co-located with the CP-SAT pipeline, since gates are part of the place→route loop.
- **Where does RoutingGate live?** `packages/temper-placer/src/temper_placer/placer/cp_sat/gates.py` — new file in the same package, imports contract types from `gate_contract.py`.
- **Where does the routing DRC test go?** `test_regression_drc.py` (new `test_golden_board_routing_drc_regression` function) — same file, same board, same DRC harness.
- **Does the loop need modification?** Minimal: `PlaceRouteLoop.run()` already calls `route_pcb()` and tracks `completion_rate`. The loop must expose the `RoutingResult.routed_pcb_content` to the gate — currently it is already on the result object, but `_route_placement()` returns `RoutingResult`. If the RouterV6Pipeline.run() does not write the routed content back to the temp file (it mutates it in-place), the adapter must capture the content after the pipeline runs. The existing `_build_routing_result()` already captures `routed_content` from the file. The loop's `_route_placement()` currently reads the routed content in the `if placements:` branch (line 455); the `else:` branch returns `_build_routing_result(result)` without content. The fix: always read the routed content from the temp file or the source path after pipeline.run().
- **How does RoutingGate map unconnected items to ConstraintDeltas?** Parse the `unconnected_items` array from kicad-cli DRC JSON. Each unconnected item references two pads. Map pad refs to component refs using the netlist. Create `SeparatedConstraint(min_distance_mm=current_gap + 0.1)` per component pair. If the same component pair appears in multiple unconnected items, deduplicate by pair.
- **What happens to the existing `RoutingCompleteGate` in `validation_gates.py`?** Unchanged. It serves the production-readiness workflow with a `RunMetrics`-based interface. The new `RoutingGate` is the contract-conformant gate for the place→route loop. They are different interfaces for different stages.

### Deferred to Implementation

- Exact net-ordering strategy if the router does not achieve 100% out of the box (current smoke test shows 15/24 in 18s with 500k max_iter — the full run needs parameter tuning to close the gap).
- Whether the temp file for kicad-cli DRC should be written to a deterministic path for debugging (vs mktemp).
- Exact ConstraintDelta deduplication logic for multiple unconnected nets referencing the same component pair.

---

## High-Level Technical Design

> *Directional guidance for review, not implementation specification.*

```
 ┌──────────────────────────────────────────────────────────────────┐
 │                      PlaceRouteLoop.run()                        │
 │                                                                  │
 │  solve_placement ──► route_pcb ──► RoutingResult                 │
 │       │                  │              │                        │
 │       │                  │       routed_pcb_content              │
 │       │                  │              │                        │
 │       ▼                  ▼              ▼                        │
 │  CpSatPlacement    RouterV6Pipeline  ┌──────────┐               │
 │  Result            .run()            │write temp │              │
 │                                      │.kicad_pcb │              │
 │                                      └────┬─────┘               │
 │                                           │                      │
 │                                           ▼                      │
 │                                kicad-cli pcb drc --format json  │
 │                                           │                      │
 │                                           ▼                      │
 │                                ┌─────────────────────┐          │
 │                                │   RoutingGate        │          │
 │                                │                     │          │
 │                                │ check(BoardState)   │          │
 │                                │  → CLEAN            │          │
 │                                │  → VIOLATIONS       │          │
 │                                │  → UNMEASURED       │          │
 │                                └─────────────────────┘          │
 │                                                                  │
 │  Gate contract types:  Gate, GateResult, GateStatus, GateStage  │
 │                         Violation, BoardState                    │
 └──────────────────────────────────────────────────────────────────┘
```

**RoutingGate flow:**
- Gate receives `BoardState` with `routed_pcb_path` set to the routed `.kicad_pcb` file.
- Gate runs `kicad-cli pcb drc --format json -o <out> <path>`.
- Exit ≠ 0 → `GateResult(UNMEASURED, error_message="kicad-cli exit N: <stderr>")`.
- Parse JSON, extract `violations` and `unconnected_items`.
- If both arrays are empty → `GateResult(CLEAN)`.
- If either has entries → populate `Violation` objects (type, components, nets, severity, threshold, description) → `GateResult(VIOLATIONS, violations=...)`.
- `to_delta()` maps `UNROUTED` violations to per-pair `SeparatedConstraint` deltas; returns `None` for clearance violations whose components are intra-component.

**Test flow:**
```
 test_golden_board_routing_drc_regression:
   1. solve_placement (30s, all constraints + CP-SAT C1/C2)
   2. _apply_placements_to_pcb → write placed PCB
   3. route_pcb(placed PCB) → RoutingResult
   4. assert completion_rate == 1.0 (internal signal)
   5. write routed_pcb_content → temp file
   6. kicad-cli pcb drc → parse JSON
   7. assert unconnected_items == 0
   8. assert total_errors == 0
   9. Decompose: placement DRC (from step 1 output) vs routed DRC (step 6)
  10. Assert routing_delta has no new placement-fixable violations
```

---

## Implementation Units

### U1. Router completion — achieve 100% net routing on F.Cu

**Goal:** Ensure `route_pcb()` routes all 24 nets on the temper board. Fix any routing gaps via parameter tuning (max_iter, net ordering) or bug fixes in the router_v6 pipeline. Measurement instrument is `kicad-cli pcb drc` with `unconnected_items = 0`.

**Requirements:** R1 (100% routing), R1a (completion_rate internal signal), R6 (F.Cu only)

**Dependencies:** Placement SSOT (2026-07-08-001 U1-U6 — CP-SAT courtyard+edge placement must produce DRC-clean placement)

**Files:**
- Investigate: `packages/temper-placer/src/temper_placer/router_v6/pipeline.py`
- Investigate: `packages/temper-placer/src/temper_placer/router_v6/astar_pathfinding.py`
- Investigate: `packages/temper-placer/src/temper_placer/router_v6/net_ordering.py`
- Potentially modify: `packages/temper-placer/src/temper_placer/router_v6/adapter.py` (capture routed_pcb_content always)
- Potentially modify: `packages/temper-placer/src/temper_placer/placer/cp_sat/loop.py` (ensure `_route_placement` captures routed content)
- Verification script: `scripts/check_router_completion.py` (temporary; manual execution)

**Approach:**
- Run `PlaceRouteLoop.run()` on the temper board with CP-SAT courtyard+edge placement.
- Inspect `RoutingResult.completion_rate` — compute nets_tried vs nets_total from the pipeline.
- If completion_rate < 1.0:
  - Verify `max_iter=500_000` is set (sweet spot from `docs/solutions/architecture-patterns/router-v6-closure-rate-100pct-2026-06-24.md`).
  - Check net-ordering: `net_ordering.py` prioritizes nets by class (HV > Power > GateDrive > Signal) and connection count. A net with low priority may be starved by routing congestion. Adjust ordering to route hardest nets first or increase the reroute loop cap.
  - Check for Numba A* kernel failures: nets with obstacles that create a no-path topology. The `_SKIP_NET_PREFIXES` filter (astar_pathfinding.py:49) skips nets starting with "unconnected-", "NC-", etc. Verify no legitimate nets are skipped.
  - Verify the minimal PCB construction in `_build_minimal_pcb()` (loop.py:492) includes all pads with correct net assignments. A missing pad assignment → net appears unrouted in DRC but the router never saw its pin.
- If completion_rate == 1.0 but kicad-cli DRC shows unconnected_items > 0:
  - The router's internal completion metric is wrong. Compare router-routed nets vs kicad-cli reported unconnected nets to identify the signal-to-ground gap.
  - Fix the measurement (likely in `_build_routing_result` or the pipeline's net-counting logic).
- Verify with `kicad-cli pcb drc` on the routed PCB: `unconnected_items` must be 0.

**Execution note:** This is the highest-risk unit. The router's pathfinding kernel (Numba) and pipeline configuration are the primary surface area. Focus on parameter tuning and net-resolution correctness, not algorithm changes.

**Test scenarios:**
- Happy path: `PlaceRouteLoop.run()` returns `completion_rate=1.0`, `kicad-cli pcb drc` reports `unconnected_items=0`.
- Happy path: All 24 temper board nets have at least one track segment on F.Cu in the routed PCB.
- Edge case: Net with only two pins — routed in one segment. Net with N pins — routed in N-1 segments.
- Edge case: A net that the router's internal bookkeeping declares "routed" but kicad-cli DRC reports as unconnected → signal-to-ground gap found and fixed.

**Verification:**
- `kicad-cli pcb drc` on routed output: `unconnected_items` array is empty.
- `RoutingResult.completion_rate == 1.0`.

---

### U2. Implement gate contract types and RoutingGate

**Goal:** Create the shared gate contract module (`gate_contract.py`) with `Gate`, `GateResult`, `GateStatus`, `GateStage`, `Violation`, `ViolationType`, `BoardState`, and `ConstraintDelta` — all per `docs/brainstorms/2026-07-08-gate-contract.md`. Implement `RoutingGate` in `gates.py` that conforms to the contract and runs kicad-cli DRC on the routed board.

**Requirements:** R4 (RoutingGate per contract), R2 (DRC error = 0 measurement)

**Dependencies:** U1 (router completion — the gate cannot pass until the router routes all nets)

**Files:**
- Create: `packages/temper-placer/src/temper_placer/placer/cp_sat/gate_contract.py`
- Create: `packages/temper-placer/src/temper_placer/placer/cp_sat/gates.py`
- Test: `packages/temper-placer/tests/placer/cp_sat/test_routing_gate.py`

**Approach:**

**Part A: gate_contract.py**
- Define `GateStage` enum: `PLACEMENT`, `ROUTING`.
- Define `GateStatus` enum: `CLEAN`, `VIOLATIONS`, `UNMEASURED`.
- Define `ViolationType` enum: `CLEARANCE`, `UNROUTED`, `LOOP_INDUCTANCE`, `THERMAL`, `CREEPAGE`, `VIA_COUNT`, `SLOP`. W1 uses only `CLEARANCE` (for track-to-track/track-to-pad violations) and `UNROUTED` (for unconnected items).
- Define `Violation` frozen dataclass with fields per the contract: `type`, `components`, `nets`, `severity`, `threshold`, `description`, `context`.
- Define `GateResult` frozen dataclass: `status`, `violations`, `error_message`.
- Define `BoardState` frozen dataclass with fields per the contract.
- Define `Gate` abstract class with `stage`, `name`, `check(state) -> GateResult`, `to_delta(violation) -> ConstraintDelta | None`.

**Part B: RoutingGate**
- `stage = GateStage.ROUTING`, `name = "routing_drc"`.
- `check(state: BoardState) -> GateResult`:
  1. Guard: if `state.routed_pcb_path` is `None`, return `UNMEASURED` with `error_message="No routed PCB path in BoardState"`.
  2. Run `kicad-cli pcb drc --format json -o <tmp> <state.routed_pcb_path>`.
  3. If exit code != 0, return `UNMEASURED` with stderr in `error_message`.
  4. Parse JSON. Extract `violations` array and `unconnected_items` array.
  5. If both are empty, return `CLEAN`.
  6. Map DRC violation entries to `Violation` objects:
     - `unconnected_items` → `Violation(type=UNROUTED, severity=1, threshold=0, ...)`
     - Track-to-track / track-to-pad clearance → `Violation(type=CLEARANCE, severity=<actual_gap>, threshold=<required_gap>, ...)`
     - Other types (silk_over_copper, etc.) → `Violation(type=CLEARANCE, ...)` with type-string in context.
  7. Return `GateResult(VIOLATIONS, violations=...)`.
- `to_delta(violation) -> ConstraintDelta | None`:
  - For `UNROUTED`: extract component refs from the pad references in the violation description, map to a `SeparatedConstraint(min_distance_mm=current_gap + 0.1)`.
  - For `CLEARANCE`: if both named refs are the same component (intra-component), return `None`. Otherwise, return a `SeparatedConstraint` between the two component refs.
  - The delta's `reason` field includes the violation type and severity for diagnostics.

**Patterns to follow:**
- `packages/temper-placer/src/temper_placer/placer/cp_sat/gate.py:74` — `AcceptanceGate` truth-gate pattern (run DRC, check error_count).
- `packages/temper-placer/src/temper_placer/validation/drc.py:53` — `DRCViolationType` enum for mapping KiCad violation types.
- `packages/temper-placer/tests/placer/cp_sat/test_regression_drc.py:46` — `_run_drc(pcb_path)` function (reuse or extract to shared utility).

**Test scenarios (test_routing_gate.py):**
- Happy path: `BoardState` with routed PCB having zero DRC errors → `GateResult(CLEAN)`.
- Happy path: `BoardState` with routed PCB having `unconnected_items` → `GateResult(VIOLATIONS)` with `UNROUTED` violations.
- Happy path: `BoardState` with routed PCB having clearance violation → `GateResult(VIOLATIONS)` with `CLEARANCE` violations.
- Edge case: `routed_pcb_path` is `None` → `GateResult(UNMEASURED)` with error message.
- Edge case: kicad-cli exit 3 (board parse failure) → `GateResult(UNMEASURED)`.
- Edge case: `to_delta` on intra-component clearance violation → returns `None`.
- Edge case: `to_delta` on inter-component unconnected net → returns `SeparatedConstraint` delta.
- Contract: `CLEAN` + empty violations ≠ `UNMEASURED` + empty violations — these are distinct states.

**Verification:**
- `GateResult(CLEAN).status == GateStatus.CLEAN` and violations is empty.
- `GateResult(UNMEASURED).error_message` is populated.
- RoutingGate correctly distinguishes the three states for a known-clean, known-dirty, and missing-input board.

---

### U3. Extend golden-board DRC gate to routing in test_regression_drc.py

**Goal:** Add `test_golden_board_routing_drc_regression` to `test_regression_drc.py` that runs the full placement + routing + DRC pipeline and asserts `unconnected_items=0` AND `total_errors=0`. Decompose routing delta from placement baseline.

**Requirements:** R3 (golden-board gate extended), R3a (routing delta decomposition), R5 (placement dependency on 001 U1-U6)

**Dependencies:** U1 (router completion), U2 (RoutingGate for reusable DRC parsing)

**Files:**
- Modify: `packages/temper-placer/tests/placer/cp_sat/test_regression_drc.py`
- Potentially extract: shared DRC utility functions to `packages/temper-placer/tests/placer/cp_sat/_drc_utils.py`

**Approach:**
- Add `test_golden_board_routing_drc_regression` (marked `@pytest.mark.slow`).
- Reuse the existing placement pipeline from `test_golden_board_drc_regression` (steps 1-6: load netclass, parse board, solve placement, write placed PCB, run placement DRC).
- After placement DRC is verified clean:
  1. Call `route_pcb()` on the placed PCB (reuse the `_route_placement` pattern from `PlaceRouteLoop` or call the adapter directly).
  2. Assert `routing_result.completion_rate == 1.0`.
  3. Write `routing_result.routed_pcb_content` to a temp file.
  4. Run `kicad-cli pcb drc` on the routed PCB.
  5. Count violations and unconnected items.
- **Assertions:**
  - `unconnected_items == 0` — every net is routed.
  - `total_errors == 0` — no DRC violations of any type on the routed board.
- **Delta decomposition (diagnostic, not blocking):**
  - Compute `routing_delta = routed_errors_by_type - placement_errors_by_type`.
  - If `routing_delta` has any placement-fixable violations (shorting_items, solder_mask_bridge), log a warning — these indicate the router corrupted the placement.
  - If `routing_delta` has clearance violations from tracks, log the net names for diagnosis.
- The test skips if `kicad-cli` is unavailable (existing pattern) or if placement fails (the placement DRC test already catches this).

**Refactoring note:** Extract the DRC-running, violation-counting, and type-classifying logic from `test_golden_board_drc_regression` into shared helper functions (`_run_drc_and_classify`, `_assert_placement_clean`) in the same test file or a `_drc_utils.py` companion. The existing test and the new routing test both call them.

**Test scenarios:**
- Happy path: Placement clean + routing clean → both assertions pass.
- Routing failure: `unconnected_items > 0` → test fails with net names.
- Routing DRC failure: `total_errors > 0` → test fails with violation types and counts.
- Delta signal: Placement has `<n>` errors, routed has `<n>` errors (all inherited) → routing_delta is zero in placement-fixable categories → test passes (zero is zero).
- kicad-cli unavailable: test skips (existing pattern).

**Verification:**
- `pytest tests/placer/cp_sat/test_regression_drc.py::test_golden_board_routing_drc_regression -v` — passes when `unconnected_items=0` and `total_errors=0`.

---

### U4. CI pipeline extension — wire routing gate into CI

**Goal:** Ensure the routing gate runs in CI so that any regression in routing completeness or routed-board DRC is caught before merge. Integrate with the existing DRC ratchet infrastructure.

**Requirements:** R3 (CI breaks on routed DRC violations), R5 (placement dependency)

**Dependencies:** U1, U2, U3 (routing must pass before CI can gate on it)

**Files:**
- Modify: `.github/workflows/drc.yml` (or equivalent CI workflow file)
- Potentially modify: `scripts/ci_check_drc.py`
- Potentially create: `scripts/ci_check_routing_drc.py`
- Modify: `packages/temper-placer/tests/placer/cp_sat/test_regression_drc.py` (add a fast-smoke variant if needed)

**Approach:**

**Option A (preferred — extend existing CI):**
- The existing CI runs `test_golden_board_drc_regression` (placement DRC gate). Add `test_golden_board_routing_drc_regression` to the same pytest invocation.
- Since the routing test depends on the placement being clean, it runs after `test_golden_board_drc_regression`. Use `@pytest.mark.depends(on=["test_golden_board_drc_regression"])` or simple ordering (pytest runs test functions in definition order by default).
- The routing test is `@pytest.mark.slow` — ensure the CI workflow has adequate timeout (route_pcb with 500k max_iter completes in ~15-20s on temper; kicad-cli DRC adds ~2-5s).

**Option B (separate CI job):**
- Create `scripts/ci_check_routing_drc.py` that runs placement + routing + DRC directly (bypassing pytest for CI speed).
- This script imports `RouteGate.check()` and asserts the result status is `CLEAN`.
- The CI workflow runs this as a separate job after the placement DRC job.

Choose Option A for W1 — it's simpler, reuses the existing test infrastructure, and the routing test is a natural extension of the placement DRC regression test.

**CI workflow changes:**
- Verify the existing DRC CI job has sufficient timeout (add 60s for routing + DRC).
- Ensure `kicad-cli` is available in the CI environment (already required for placement DRC).
- Add the routing gate test name to the pytest invocation: `-k "test_golden_board_drc_regression or test_golden_board_routing_drc_regression"`.

**Ceiling integration (future):**
- The `DrcRatchet` infrastructure in `drc_ratchet.py` supports per-board error ceilings. After W1, the routed board gets a ceiling entry in `drc_ceiling.json`: `{"temper_routed": {"total_errors": 0, "unconnected_items": 0}}`. This is a follow-up task (deferred to W2 when multi-layer routing may introduce legitimate violations that need ceiling tracking).

**Test scenarios:**
- CI passes: placement clean, routing clean.
- CI fails: routing has unconnected items → red build, error message names the nets.
- CI fails: routing introduces DRC violations → red build, delta decomposition shows which types.
- CI skips: kicad-cli not available in CI environment.

**Verification:**
- `gh pr checks` shows the DRC job passing with both placement and routing gates green.

---

## System-Wide Impact

- **Interaction graph:** `PlaceRouteLoop.run()` → `_route_placement()` → `route_pcb()` → `RouterV6Pipeline.run()` produces a `RoutingResult` with `routed_pcb_content`. RoutingGate reads this content and runs kicad-cli DRC. The test in `test_regression_drc.py` exercises the full chain. No changes to the placement model or constraint encoding.
- **Error propagation:** If the router fails to route all nets, the routing gate returns `VIOLATIONS` with `UNROUTED` violations. The `to_delta()` method maps these to `SeparatedConstraint` deltas — the W5 compound loop can inject these into the next placement round. If kicad-cli crashes, the gate returns `UNMEASURED` — the loop surface the error and blocks convergence.
- **State lifecycle:** `BoardState` is constructed once per loop round from the placement and routing results. It is frozen (dataclass, no mutation). The gate reads it and produces a `GateResult` — the gate does not mutate state.
- **Unchanged invariants:** The CP-SAT model, PCL constraints, placement encoder, and router_v6 pipeline internals are unchanged. The gate is a measurement layer on top of the existing pipeline.
- **Performance:** Routing with max_iter=500_000 on the temper board takes ~15-20s. kicad-cli DRC on the routed board adds ~2-5s. Total CI time increase: ~20-25s over the existing placement DRC gate. Acceptable for a slow test.

---

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| Router cannot achieve 100% completion on F.Cu with current config | Parameter tuning path: adjust max_iter sweet spot, reorder nets (hardest first), fix net-resolution bugs. If the Numba A* kernel has a topological limitation, escalate to a router fix ticket (not a W1 blocker — document the gap and set a ratchet ceiling). |
| Router reports 100% but KiCad DRC shows unconnected items | This is a signal-to-ground gap — the router's internal completion metric is wrong. Fix the measurement in `_build_routing_result` or the pipeline's net-counting logic. The gate's `UNMEASURED` status surfaces this as a measurement failure. |
| Placement DRC target not yet at ≤22 (W0 U6 incomplete) | W1 depends on placement being DRC-clean. If U6 is not complete, the routing gate test will fail on placement-inherited violations, not routing bugs. Fix: wait for U6 or run routing on the human-verified placement as a fallback. |
| kicad-cli JSON output format changes between versions | The DRC parsing code already handles KiCad JSON (`test_regression_drc.py`). The routing gate reuses the same parsing with additional `unconnected_items` handling. Version-lock kicad-cli if needed. |
| CI timeout for routing + DRC is too high | max_iter=500_000 is the sweet spot; increase CI timeout to 3 min for the DRC job. Smoke tests show 15/24 in 18s; full routing should complete under 60s. |
| `routed_pcb_content` not populated in the `else:` branch of `_route_placement` | Fix: always read the routed content from the temp file after `pipeline.run()`, not just in the `if placements:` branch. This is a one-line fix in `adapter.py` or `loop.py`. |

---

## Sources & References

- **Origin document:** [docs/brainstorms/2026-07-08-single-layer-route-requirements.md](../brainstorms/2026-07-08-single-layer-route-requirements.md)
- **Gate contract:** [docs/brainstorms/2026-07-08-gate-contract.md](../brainstorms/2026-07-08-gate-contract.md)
- **Placement plan:** [docs/plans/2026-07-08-001-feat-cp-sat-courtyard-edge-constraints-plan.md](2026-07-08-001-feat-cp-sat-courtyard-edge-constraints-plan.md)
- `packages/temper-placer/src/temper_placer/placer/cp_sat/loop.py` — `PlaceRouteLoop`, `_route_placement`, `_build_minimal_pcb`
- `packages/temper-placer/src/temper_placer/router_v6/adapter.py` — `route_pcb`, `RoutingResult`, `_build_routing_result`
- `packages/temper-placer/tests/placer/cp_sat/test_regression_drc.py` — golden-board placement DRC gate
- `packages/temper-placer/src/temper_placer/validation/drc.py` — `DRCViolationType`, DRC parsing
- `packages/temper-placer/src/temper_placer/regression/drc_ratchet.py` — `DrcRatchet` CI infrastructure
- Learning: `docs/solutions/architecture-patterns/router-v6-closure-rate-100pct-2026-06-24.md`
- Learning: `docs/solutions/architecture-patterns/cp-sat-constraint-encoder-greenfield-hard-ceiling-2026-07-05.md`
- Learning: `docs/solutions/architecture-patterns/two-tier-acceptance-gate-unsat-surfacing-2026-07-05.md`
