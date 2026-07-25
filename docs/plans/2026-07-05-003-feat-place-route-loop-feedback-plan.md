---
type: feat
origin: docs/brainstorms/2026-07-05-place-route-loop-feedback-as-constraint-requirements.md
status: abandoned
swept: 2026-07-25
swept_basis: "only 0/11 named paths exist"
---
# feat: Place→Route Loop — Router Feedback as CP-SAT Constraints

## Summary

Wire CP-SAT placement output through `router_v6` and close the loop: when congestion or unroutable regions surface, encode the router's signal as new CP-SAT hard constraints (clearance increase, keepout around unrouted pins, rotation adjustments) and re-solve in feasibility-budget time. Decisive result: a CP-SAT placement round-trips through `router_v6` to completion ≥ 90% on the temper board, with the loop automatically backtracking on infeasible feedback (closed-loop policy, per user decision).

**Scale:** New ~300-line feedback-classifier module, modified CP-SAT encoder to accept runtime constraint deltas, integration test for the round-trip loop. Existing infrastructure: `route_pcb()` at `router_v6/adapter.py:316`, `_apply_placements_to_pcb()` at line 402, `PlacementResult` from `placer/deterministic.py`.

---

## Problem Frame

Placement is solved (post-constraint-completion, 8/8 types + rotation); routing has remained untouched throughout the paradigm swap. CP-SAT's instant re-solve (~0.1s feasibility) is the second dividend of the paradigm: where JAX needed "retune weights and re-descend" to react to routing failure, CP-SAT needs "add a hard constraint and re-solve in 0.1s." The feedback-class vocabulary — what categories of `router_v6` signal become what categories of CP-SAT constraint — is this workstream's actual design surface.

Three pieces of infrastructure are in place: `route_pcb()` at `router_v6/adapter.py:316`, `_apply_placements_to_pcb()` at line 402, and the CP-SAT placement output's `PlacementResult` (from the constraint-completion workstream). What's net-new is the feedback-class vocabulary and the loop controller that orchestrates place→route→measure→feedback→re-place round-trips.

---

## Implementation Units

### U1. Verify the Place→Route Seam End-to-End (Baseline)

**Goal:** Run `router_v6` on a CP-SAT placement and measure the un-looped baseline completion rate. This establishes whether the feedback loop is even necessary.

**Requirements:** R1 (round-trip measurement producing completion_rate, unrouted_nets, drc_violations)

**Dependencies:** F2 constraint-completion workstream complete (CP-SAT produces valid placements with 8/8 types + rotation)

**Files:**
- Create: `tests/placer/cp_sat/test_router_integration.py` — baseline measurement test
- Modify: `src/temper_placer/placer/cp_sat/encoder.py` — add `PlacementResult` → PCB application step (via `_apply_placements_to_pcb`)

**Approach:**
1. Run CP-SAT solver on temper board → get `PlacementResult` (positions dict + rotation indices)
2. Convert to placed PCB: write placement to `.kicad_pcb` via existing `kicad_writer` or use `_apply_placements_to_pcb` in-memory
3. Run `route_pcb()` from `router_v6.adapter`
4. Collect `RoutingResults.compile_routing_results()` → completion_rate, unrouted_nets list, DRC violations from `drc_runner.run_drc()`
5. Record the baseline: what completion rate does router_v6 achieve on a good CP-SAT placement WITHOUT any feedback loop?

**Test scenarios:**
- CP-SAT placement on temper → `_apply_placements_to_pcb` → `route_pcb()` completes without errors
- `RoutingResults` parsed into structured completion_rate, unrouted_nets, drc_violations
- Baseline completion rate recorded (expected: unknown — this is the measurement)

**Verification:** The place→route→measure pipeline runs end-to-end. If baseline completion ≥ 90%, the feedback loop may be unnecessary (but is still built as infrastructure). If baseline < 90%, the loop is justified.

---

### U2. Build the Feedback-Classifier Module

**Goal:** Create the feedback-class vocabulary — the mapping from `router_v6` routing results to CP-SAT constraint deltas. This is the workstream's actual design output.

**Requirements:** R2 (feedback-class vocabulary: 4 classes minimum, injected through normal PCL encoder — no special path)

**Dependencies:** U1 (routing results available as structured data)

**Files:**
- Create: `src/temper_placer/placer/cp_sat/feedback.py` — `FeedbackClassifier`, `ConstraintDelta`, four feedback class handlers
- Create: `tests/placer/cp_sat/test_feedback.py` — per-class classification tests

**Approach:**

```python
@dataclass
class ConstraintDelta:
    """A constraint to add/tighten in the next CP-SAT solve."""
    constraint_type: ConstraintType
    spec: dict  # constraint-specific params
    reason: str  # router signal that produced this delta

class FeedbackClassifier:
    def classify(self, routing_results: RoutingResults, placement: PlacementResult) -> list[ConstraintDelta]:
```

Four feedback classes:

**Class 1 — Congestion in a corridor:** `RoutingResults` shows unrouted nets clustered in a region between two components.
→ Inject `SeparatedConstraint(a=comp_a, b=comp_b, min_distance_mm=current + 1.0)` to widen the channel OR `KeepoutConstraint(zone=congestion_bbox, margin=0.5)` to push the router to an alternate path.
Decision: prefer `SeparatedConstraint` (simpler, directly addresses the cause); `KeepoutConstraint` as fallback if separation doesn't resolve in 2 rounds.

**Class 2 — DRC clearance violation:** Two placed components violate the post-route DRC clearance check.
→ Inject `SeparatedConstraint(a=violation.comp_a, b=violation.comp_b, min_distance_mm=violation.required_mm)` — replaces any weaker prior separation. CP-SAT's hard constraint IS the correction.

**Class 3 — Unrouted critical pin:** A pin on a critical IC (Q1, Q2 — IGBTs) can't be routed.
→ Inject `AnchoredConstraint(component=ic_ref, position=heuristic_optimal_position)` where the position is determined by a shortest-path heuristic pre-route on the unrouted net. Forces CP-SAT to choose a topologically favorable placement for that component.

**Class 4 — Persistent high-pin-count IC failure:** Same IC has remaining unrouted pins after 3+ rounds.
→ Inject rotation coordination: if the IC has a dense side, force a rotation that presents the less-dense side to the routing channel. Interacts with the constraint-completion workstream's discrete rotation model — the rotation coordination is a `rot_ref` domain restriction.

**Unclassified failures:** If a routing failure doesn't match any class → log the failure with full context and surface it as a diagnostic. Do not silently burn round-trip budget.

Each constraint delta is injected through the normal PCL encoder — the encoder doesn't know the constraint came from feedback vs. from the PCL spec.

**Test scenarios:**
- Routing with 2 congested nets between Q1 and Q2 → classifier produces SeparatedConstraint delta with increased min_distance_mm
- Routing with clearance violation at 5.8mm (required 6.0mm) → SeparatedConstraint delta with min_distance_mm=6.0
- Routing with unrouted pin on Q1 → AnchoredConstraint delta with heuristic position
- Routing with 4 consecutive rounds of unrouted pins on Q1 → rotation coordination delta
- Routing with unclassified failure → logged diagnostic, no delta produced (counted as unclassified)
- All deltas are valid `ConstraintType` values dispatchable through `encoder.TYPE_HANDLERS`
- Covers AE2, AE3. Deltas inject through normal PCL encoder; rotation constraint variant comes from feedback vocabulary.

**Verification:** Feedback classifier produces valid ConstraintDeltas; deltas encode without errors through the CP-SAT encoder.

---

### U3. Build the Loop Controller with Closed-Loop Backtracking

**Goal:** Build the `PlaceRouteLoop` controller that orchestrates the round-trip: place → route → measure → classify → re-place. Implements closed-loop automatic backtracking: on UNSAT from injected feedback, try the next-strongest signal; if all feedback signals fail, surface the UNSAT core to the operator.

**Requirements:** R3 (≤1s re-solve, ≤5s worst; two-phase solve; N=10 cap), R5 (infeasible-feedback with closed-loop backtracking)

**Dependencies:** U1 (baseline measurement), U2 (feedback classifier)

**Files:**
- Create: `src/temper_placer/placer/cp_sat/loop.py` — `PlaceRouteLoop` controller class
- Create: `tests/placer/cp_sat/test_loop.py` — loop behavior tests

**Approach:**

```python
class PlaceRouteLoop:
    MAX_ROUNDS: int = 10
    
    def run(self, board_config, pcl_constraints) -> LoopResult:
        for round in range(self.MAX_ROUNDS):
            # 1. Solve CP-SAT with current constraint set
            placement = self.solve_phase1(pcl_constraints + injected_deltas)
            
            # 2. Place → route → measure
            routing = self.route_and_measure(placement)
            
            # 3. Check termination
            if routing.completion_rate == 1.0 and routing.drc_errors == 0:
                if self.consecutive_stable_rounds >= 2:
                    placement = self.solve_phase2(placement)  # wirelength polish
                return LoopResult(success=True, placement=placement)
            
            # 4. Classify feedback
            deltas = self.classifier.classify(routing, placement)
            if not deltas:
                return LoopResult(success=False, reason="no_classifiable_feedback")
            
            # 5. Try deltas — closed-loop backtracking
            for delta in deltas:
                try:
                    test_placement = self.solve_with_delta(pcl_constraints, injected_deltas + [delta])
                    if test_placement is not UNSAT:
                        injected_deltas.append(delta)
                        break  # found a workable delta
                except UnsatError as e:
                    # Closed-loop: try next-strongest signal
                    continue
            else:
                # All deltas produced UNSAT — surface to operator
                return LoopResult(success=False, reason="all_feedback_unsat",
                                  unsat_core=self.extract_unsat_core())
        
        return LoopResult(success=False, reason="round_limit_exceeded")
```

**Closed-loop backtracking policy (user decision — resolved):**
- When an injected constraint delta produces UNSAT, the loop automatically tries the next-strongest feedback signal
- If ALL feedback signals for a given routing failure class produce UNSAT, the loop surfaces the UNSAT core with a structured diagnostic (which constraints conflict, why they conflict)
- The loop does NOT auto-loosen physics-grounded constraints (loop-area ceiling, thermal anchoring) — those are HARD per the L_loop derivation
- The loop terminates on: completion=100% AND DRC=0 AND phase-2 exhausted; OR round-trip cap N=10; OR unclassifiable routing failure; OR all-feedback-UNSAT

**Two-phase solve policy (from origin):**
- Phase 1 (feasibility): every round-trip, ≤1s target
- Phase 2 (bounded wirelength polish): runs only after two consecutive feasibility-stable round-trips (heuristic: the constraint set is mature enough to polish)
- Phase 2 polish must not regress completion rate below phase 1's

**Constraint delta application:**
- Fresh model per round-trip with `AddHint` from the previous placement for warm-start (OR-Tools push/pop may not preserve performance for this constraint class)
- If OR-Tools incremental API works: benchmark both approaches and use the faster one

**Test scenarios:**
- Clean placement (no routing failures) → loop exits after 1 round with success
- One clearance violation → loop injects SeparatedConstraint, re-solves, violation closed → exits with success after 2 rounds
- Injected delta produces UNSAT → loop tries next-strongest signal → finds workable delta → success (closed-loop backtracking)
- All deltas produce UNSAT → loop exits with unsat_core diagnostic
- N=10 rounds without convergence → loop exits with round_limit_exceeded
- Phase 2 polish triggers after 2 stability rounds → completion doesn't regress
- Covers AE4. Two stability rounds → phase-2 polish before re-routing; completion after phase-2 doesn't regress.
- Covers AE5. Feedback-injection UNSAT → core report + automatic backtracking.

**Verification:** Loop terminates correctly on all exit conditions; re-solve time ≤1s per round; closed-loop backtracking works on temper board.

---

### U4. Integrate the Loop into the CLI Pipeline

**Goal:** Wire the `PlaceRouteLoop` into the `temper optimize` CLI command so the full place→route loop runs automatically.

**Requirements:** R4 (decisive result: completion ≥ 90% on temper)

**Dependencies:** U3 (loop controller working)

**Files:**
- Modify: `src/temper_placer/cli/__init__.py` — add loop integration to `optimize` command (or add `--loop` flag)
- Modify: `src/temper_placer/pipeline/orchestrator.py` — replace single-pass CP-SAT with loop invocation (or add a separate loop stage)
- Create: `tests/integration/test_place_route_loop_temper.py` — decisive-result test

**Approach:**
- Add `--loop` / `--no-loop` flag to `temper optimize` (default: loop enabled)
- In the pipeline: after CP-SAT placement, if loop is enabled, invoke `PlaceRouteLoop.run()`
- The loop produces a final placement + routing result with completion rate and DRC status
- Surface the result: `temper optimize` output includes "Routing completion: XX.X% (0 DRC errors)" or "Routing incomplete: XX.X% — see diagnostics"

**Test scenarios:**
- `temper optimize --no-loop` — runs CP-SAT placement only (existing behavior)
- `temper optimize --loop` — runs full place→route loop, surfaces completion rate
- Covers AE1. First run achieves ≥90% or iterates toward ≥90%.
- Covers R4 decisive result: "CP-SAT placement round-trips through router_v6 to completion ≥ 90% on temper."

**Verification:** `temper optimize --loop` on temper board converges to ≥90% completion; output includes structured routing diagnostics.

---

## Key Technical Decisions

1. **Feedback classes are normal PCL constraint types, injected through the same encoder — no special "routing constraint" path.** Congestion becomes `SeparatedConstraint`; clearance violation becomes `SeparatedConstraint`-stronger; unrouted critical pin becomes `AnchoredConstraint`; high-pin persistent failure becomes rotation coordination. The encoder doesn't know the constraint came from feedback vs. from PCL. (see origin: Key Decisions)

2. **Closed-loop automatic backtracking — resolved by user decision.** When an injected constraint delta produces UNSAT, the loop automatically tries the next-strongest feedback signal. If all signals fail, surface the UNSAT core as a structured diagnostic. The loop never auto-loosens physics-grounded constraints. (see origin: Outstanding Questions resolved before planning)

3. **Fresh model per round-trip with AddHint warm-start.** OR-Tools `push()/pop()` may not preserve performance for the constraint classes this workstream injects. `AddHint` from the previous placement is the safe default; benchmark both and use the faster approach. (see origin: Deferred to Planning — incremental-solver strategy)

4. **Phase 2 wirelength polish runs on stability, not every round-trip.** The first rounds are feedback-driven (feasibility-first → re-solve for constraint delta). Phase 2 adds value only when the constraint set is converging — running it before wastes 60s on a placement the classifier will revise. (see origin: Key Decisions)

5. **No physics-constraint loosening for routability — HARD BLOCKER.** The L_loop ceiling stays hard; thermal anchoring stays hard. The documented backtracking surface is "next-strongest feedback signal or operator relief" — never "auto-loosen a physics constraint." (see origin: Key Decisions)

---

## Scope Boundaries

### Deferred for Later

- Pushing routing completion from 90% toward 100% — follow-up workstream if feedback vocabulary proves insufficient (see origin)

### Deferred to Follow-Up Work

- Congestion-heatmap visualization (router_v6 may not produce a usable heatmap; deriving congestion bounding-boxes from unrouted-net geometry may be necessary)
- `AnchoredConstraint` empirical effectiveness measurement on critical pins
- Interactive autorouter paths (the loop is automated, not interactive)

### Outside This Product's Identity

- router_v6 replacement or improvement — the loop wraps router_v6 as-is
- Two-phase solve's objective mechanism — governed by the umbrella's Objective-Discipline Contract (wirelength only)
- Multi-board generalization (rp2040, bitaxe, piantor) — decisive result is temper-specific

---

## Dependencies / Prerequisites

- **F2 constraint-completion workstream complete** — hard prerequisite: the loop iterates placements with all 8 PCL constraint types honored + rotation. ANCHORED and KEEPOUT handlers must be functional (feedback classes inject these types).
- **F1 JAX-retirement workstream complete** — `router_v6/pipeline.py` may have JAX dependencies removed during the deletion. The loop depends on `router_v6.adapter.route_pcb()` being functional post-JAX-deletion.
- `PlacementResult` from `placer/deterministic.py` (or CP-SAT equivalent) — consumed by `_apply_placements_to_pcb`
- `drc_runner.run_drc()` on routed PCB — verified functional (requires `kicad-cli`)
- OR-Tools warm-start via `AddHint` — functional in OR-Tools 9.x

---

## Risks

| Risk | Mitigation |
|------|-----------|
| Baseline completion rate unknown — loop may be unnecessary | U1 measures baseline first; if ≥90%, loop is infrastructure-only (still built, but not gated on it) |
| Feedback vocabulary incomplete — real routing failures outside 4 classes | U2: unclassified failure diagnostic and round-counting; if >50% failures unclassified after 3 rounds, abort with diagnostic |
| Incremental solver push/pop unsupported → re-solve exceeds ≤1s budget | U3: `AddHint` warm-start as default; benchmark to verify budget |
| Loop oscillates — constraint deltas toggle between two placements | U3: detect oscillation (same placement + delta repeats within 3 rounds); abort with diagnostic |
| router_v6 is the bottleneck, not placement quality | U1 baseline measurement reveals whether router quality or placement quality limits completion |
| Physics constraints (tol=0 loop area) prevent routing closure | U3: surfaced as structured UNSAT diagnostic; the operator must decide whether to loosen (the loop never auto-loosens) |

---

## Test Strategy

- **Unit tests:** Feedback classifier (U2) tested with mock routing results for each feedback class.
- **Integration tests:** Loop controller (U3) tested with real CP-SAT solve + mock routing (to control round-trip behavior without requiring a full router_v6 setup).
- **End-to-end test:** U4 runs the full place→route loop on the temper board to verify the ≥90% decisive result.
- **UNSAT path test:** Artificially over-constrained delta → verify backtracking fires and next-strongest signal is tried.
