---
title: Minimum-Displacement Clearance Repair Loop (issue #504)
type: feat
date: 2026-07-31
topic: clearance-repair-loop
artifact_contract: ce-unified-plan/v1
artifact_readiness: active
product_contract_source: ce-brainstorm
execution: code
---

# Minimum-Displacement Clearance Repair Loop (issue #504)

## Goal Capsule

Ship the **machinery** for route-aware clearance repair: a minimum-displacement
repair mode for the CP-SAT placement pipeline that re-solves a routed board
*close to its current positions* (Manhattan-displacement objective, rotations
pinned, optional hard displacement envelope), plus the reinforcement loop that
drives independent-checker-flagged inter-component REQ-SAFE-01 pairs to zero
and **reports infeasibility honestly**. This PR lands no board change: the
board-output workstream (issue #517) consumes this machinery; `pcb/` and
`power_pcb_dataset/` are untouched here.

## Problem Frame

The routed board carries **123 REQ-SAFE-01 clearance/creepage violations across
79 pairs** at the enforced 12.6mm reinforced margin (PD3; measured 2026-07-31
on origin/main `4a387393e`). A free CP-SAT reshuffle clears the movable pairs
but reproducibly regresses routed DRC (`shorting_items`/`unconnected_items`
rise) because it moves nearly every component away from its routed copper
(`docs/evidence/2026-07-30-copper-aware-domain-resolve.md`). Issue #504
requires a **minimum-displacement or route-aware placement/re-routing loop**
instead of writing the free reshuffle into the routed PCB.

## Approach (ce-brainstorm outcome)

Three candidate mechanisms were evaluated:

1. **Existing loop** (`PlaceRouteLoop`) — a place→route→recheck pipeline, not a
   repair mode; no min-displacement objective exists anywhere in the encoder
   (grep-verified: zero hits for displacement/repair machinery before this
   branch).
2. **New hard constraint only** — a displacement bound without an objective:
   works for "no component may move > B" but cannot express "move as little as
   possible" and silently fails when the bound is infeasible.
3. **Objective + optional bound + reinforcement loop (chosen)** — the
   minimum-displacement objective is a *preference* (hard constraints stay
   authoritative); `max_displacement_mm` adds the hard envelope when a caller
   needs a guarantee; the reinforcement loop re-checks every solve with the
   *independent* copper-to-copper checker and hard-constrains any pair it
   still flags. Regression-guarded against the never-landed PR #498 no-op
   (objective terms were registered but `Minimize` was never called on the
   encoder solve path).

### R24 discipline for the new objective/bound

- **Soundness proof**: the objective is not a physics-gating constraint. When
  `max_displacement_mm` is used it becomes a hard *geometry* bound on Manhattan
  displacement (`|dx| + |dy| <= B`, exact in grid units) — a placement-model
  quantity, not a physics quantity; the proof is the trivial AddAbsEquality
  identity. The physics-gating part — the domain-clearance `SeparatedConstraint`
  — carries its own Chebyshev-style box-separation soundness proof (revised
  copper-aware 2026-07-30, `domain_clearance.py` module docstring) plus the
  R24 post-solve audit (`audit_domain_clearance`).
- **BMC-exhaustive validation on small N**: `TestDisplacementObjectiveBMC`
  compares the solver's displacement against a closed-form truthful oracle over
  a grid of reference points (25 hypothesis cases); `test_solver_breaks_
  infeasible_reference_with_minimal_moves` pins the exact proven optimum
  (total = 60mm by `|u - v| <= |u| + |v|`); `test_hard_displacement_bound_*`
  pin bound-respected and bound-infeasible behavior.
- **Post-solve audit**: `run_clearance_repair_solve` runs
  `audit_domain_clearance` on every round's resolved coordinates AND re-checks
  with `verify_iec60335_compliance` (the independent gate checker); the
  real-board test asserts both are clean.

### Loop invariant and termination (induction)

- Invariant: every round's constraint set contains a hard `SeparatedConstraint`
  for every pair the previous round's independent check flagged.
- Base case: the full domain-clearance set from the same classifier the checker
  uses (imported, not reimplemented) + unclassified-near-HV keep-away
  constraints mirroring the fixture's fail-closed proximity check.
- Induction: a round either reaches 0 inter violations or adds >= 1 new
  constraint; distinct inter pairs are finite (<= N²), so the loop terminates
  in at most (distinct pairs) + 1 rounds. A flagged pair whose hard constraint
  was SAT in the same round contradicts the box-separation soundness proof →
  terminate immediately with status `"gap"` (never silently claim success).

## Success Criteria

1. `solve_placement(minimize_displacement_to=..., fixed_rotations=...,
   max_displacement_mm=...)` steers the solve (regression test pins the
   objective is actually applied); determinism: same input + seed → same output.
2. `run_clearance_repair_solve` on the real routed board reports, verified by
   the independent copper-to-copper checker: inter-component violations
   **0**, intra-footprint blockers enumerated (not claimed fixed), audit 0,
   termination within max_rounds, displacement reported.
3. Bounded repair reports infeasibility honestly (UNSAT core surfaced) rather
   than converging to nothing.
4. All gates green on the touched Python: ruff, import-linter, existing
   placer/cp_sat suite (no new failures beyond the documented pre-existing
   `test_regression_drc.py` corpus-copy pair).

## Out of Scope (ownership)

- No `pcb/temper.kicad_pcb` change on any pushed branch (board output belongs
  to the #517 workstream).
- No `power_pcb_dataset/drc_ceiling.json` change (DRC ceiling protocol belongs
  to #517).
- No re-routing pass; the machinery produces placements for the board
  workstream to evaluate.

## Timebox & Rollback

- Timebox: one session (~4-6h incl. the 600s/180s characterization solves).
- Rollback: the branch is pure additive (new module + opt-in parameters + new
  tests); `git revert` of the single commit restores main behavior. No gate is
  weakened, skipped, or allowlisted.
