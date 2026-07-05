---
module: temper_placer
date: "2026-07-05"
problem_type: architecture_pattern
component: placer
severity: high
applies_when:
  - "When building a closed-loop system that feeds output measurements back as input constraints"
  - "When downstream tool output (router failures) must be encoded as upstream solver constraints"
  - "When re-solve budget is tight (~1s) and constraint deltas must be injected incrementally"
symptoms:
  - "Router produces detailed failure data (unrouted nets, DRC violations, congestion) but adapter discards it"
  - "Feedback constraints accumulate monotonically causing UNSAT from over-constraint"
  - "Some constraint types (KeepoutConstraint) are silently ignored by the encoder"
root_cause: integration_seam
resolution_type: architecture_pattern
tags:
  - place-route-loop
  - feedback-loop
  - constraint-delta
  - closed-loop-backtracking
  - router-integration
  - cp-sat-re-solve
---

# Place→Route Loop: Router Feedback as CP-SAT Constraint Deltas

## Problem

Placement quality and routability are coupled: a placement that satisfies all geometric constraints may still produce unroutable regions. Router failure signals — unrouted nets, DRC clearance violations, congestion hotspots — need to be fed back to the placer as additional constraints. The paradigm dividend is CP-SAT's instant re-solve (~0.1s): where JAX needed "retune weights and re-descend," CP-SAT needs "add a hard constraint and re-solve."

## Solution

### 1. RoutingResult must carry failure data

**Critical finding during review**: The `route_pcb()` adapter at `router_v6/adapter.py:392` returned `RoutingResult(completion_rate=...)` — discarding all failure data. The `RouterV6PipelineResult` carries `stage4.routing_results` with `failed_nets`, per-net success/failure, and per-net DRC violations, but none of this reached the feedback classifier.

The fix extends `RoutingResult` with `unrouted_nets`, `drc_violations`, and `congestion_regions` fields, populated from the router pipeline result and manufacturing report. The `FeedbackClassifier` already read these via `getattr(..., default=[])` — it was always getting empty defaults.

### 2. Feedback-class vocabulary maps router signals to PCL constraints

Four feedback classes, all injected through the normal PCL encoder (no special routing-constraint path):

| Router Signal | Constraint Delta | Encoding |
|--------------|-----------------|----------|
| Congested corridor between two components | `SeparatedConstraint(min_distance_mm += 1.0)` | Widens the channel |
| DRC clearance violation | `SeparatedConstraint(min_distance_mm = violated_mm)` | Replaces weaker prior separation |
| Unrouted critical pin | `AnchoredConstraint(position = heuristic_optimal)` | Forces topologically favorable placement |
| Persistent high-pin-count IC failure (>3 rounds) | Rotation coordination (restrict `rot_ref` domain) | Presents less-dense side to routing channel |

**Unclassified failures**: if a routing failure matches no class, it's logged with full context. The loop does not silently burn round-trip budget.

### 3. KeepoutConstraint must actually be encoded

**Critical finding during review**: The CP-SAT encoder's `_encode_extra_constraints` had `pass  # Keepout handled as a no-place zone` for `KeepoutConstraint`. Feedback-created congestion keepouts were silently discarded — accepted by the backtracking loop but having zero effect on placement.

The fix implements `_encode_keepout_constraint` with three resolution strategies:
1. **Named board zones**: look up zone bounds from `board.zones` when `zone_type="keepout"`
2. **Synthetic congestion names**: parse bbox from `congestion_xmin_ymin_xmax_ymax` naming convention
3. **Unresolvable fallback**: `logger.warning()` instead of silent `pass`

Each component gets the constraint `NOT (inside_keepout_bbox)` via `OnlyEnforceIf` with four auxiliary Boolean variables.

### 4. Closed-loop backtracking with delta deduplication

**Backtracking policy (resolved: closed-loop automatic)**:
- When injected delta produces UNSAT, loop tries next-strongest feedback signal
- If ALL signals for a given failure class produce UNSAT, surface UNSAT core as structured diagnostic
- Loop NEVER auto-loosens physics-grounded constraints (loop-area ceiling, thermal anchoring)

**Critical finding during review**: `injected_deltas` grew monotonically across rounds without pruning. Old deltas from round 2 could still be active in round 8, accumulating into an over-constrained set that caused UNSAT even though each individual delta was fine.

The fix adds `_deduplicate_deltas()` called at the top of each round, deduplicating by `constraint.id`. Same component pair generating the same feedback across multiple rounds only adds one constraint.

### 5. Phase-2 polish runs on stability, not every round

- Phase 1 (feasibility): every round-trip, ≤1s target
- Phase 2 (bounded wirelength polish): only after two consecutive feasibility-stable round-trips
- Phase 2 must not regress completion rate below phase 1's
- Loop terminates on: completion=100% AND DRC=0 AND phase-2 exhausted; OR round-trip cap N=10; OR unclassifiable failure; OR all-feedback-UNSAT

## Loop Termination Conditions

| Exit | Condition | Action |
|------|-----------|--------|
| Success | completion=100% AND DRC=0 AND phase2 run | Return final placement |
| Round cap | N=10 without convergence | Surface diagnostic: which signals were injected, which remain |
| Unclassifiable | Failure matches no vocabulary class | Surface diagnostic: unclassified failure with full router context |
| All-feedback-UNSAT | Every delta for a failure class produces UNSAT | Surface UNSAT core for each rejected delta |
| Oscillation | Same placement + delta repeats within 3 rounds | Abort with diagnostic |

## Key Decisions

- **Feedback classes are normal PCL constraint types**: injected through the same `encoder.TYPE_HANDLERS` dispatch. Special-casing feedback would create the silent-guard-condition failure pattern.
- **No physics-constraint loosening for routability**: the L_loop ceiling stays hard; thermal anchoring stays hard. The documented backtracking surface is "next-strongest signal or operator relief" — never "auto-loosen."
- **Fresh model with AddHint warm-start per round**: OR-Tools push/pop may not preserve performance for constraint deltas. `AddHint` from the previous placement is the safe default.

## Files Affected

- `placer/cp_sat/feedback.py` (new) — FeedbackClassifier, ConstraintDelta, 4 classes
- `placer/cp_sat/loop.py` (new) — PlaceRouteLoop, backtracking, dedup
- `placer/cp_sat/encoder.py` — `_encode_keepout_constraint`, delta injection
- `router_v6/adapter.py` — `RoutingResult` extended with failure data
- `cli/__init__.py` — `--loop`/`--no-loop` flag

## See Also

- `docs/solutions/architecture-patterns/silent-guard-condition-infrastructure-failure-pattern-2026-07-02.md` — why feedback classes must not be silently ignored
- `docs/solutions/logic-errors/unsound-atmostk-capacity-encoding.md` — why feedback constraints must be hard, not soft
