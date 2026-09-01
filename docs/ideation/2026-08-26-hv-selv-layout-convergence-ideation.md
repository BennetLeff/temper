# HV↔SELV layout convergence after the nudge falsifier

**Date:** 2026-08-26
**Status:** recommendation accepted; feasibility evaluator implemented
**Input state:** `main` after PR #1521 (`dfdfe20de`)

## Objective

Close the remaining mains/HV↔SELV safety gaps without creating an endless
sequence of component nudges that merely transfers violations between DRC
categories.

## Evidence that constrains the answer

- PR #1521 was a Pareto improvement: actionable body-free pairs fell from 8 to
  5 and total KiCad DRC errors fell from 413 to 409.
- A subsequent uncommitted trial moved U13, R43, R4, and U6. It reduced the five
  actionable pairs to zero and creepage errors from 103 to 99, but total DRC
  errors rose from 409 to 413. It added shorting, hole-clearance, solder-mask,
  and courtyard findings. The trial was discarded.
- A straight full-board isolation corridor is already an empirical NO-GO within
  the 25 mm/component budget. The best measured one-bend corridor still needed
  83.5 mm maximum displacement, 76 movers, and 3537 mm total displacement.
- The current exact-pair baseline is 93 pairs below 12.6 mm: 5 body-free, 87
  body-crossing, and 1 with unknown body geometry. The 87 body-crossing pairs
  depend on the Annex L closed-end slot interpretation packaged for a
  certification lab.

These results reject both extremes: neither repeated independent nudges nor a
global two-domain floorplan is a bounded incremental solution.

## Non-negotiable convergence contract

A proposed board change is acceptable only if all of these hold against the
same clean base and correctly configured instruments:

1. No new HV↔SELV pair below the governing threshold.
2. Total KiCad DRC errors do not rise.
3. No DRC category rises unless the increase is independently attributed and
   explicitly approved; shorting, clearance, hole-clearance, and copper-edge
   findings are hard vetoes for this work.
4. Routed-pad connectivity and local functional topology remain intact, or the
   proposal includes the corresponding reroute.
5. Courtyard/body collisions do not rise.
6. The proposal has a named region, component set, displacement budget, and
   maximum number of trials.

This is a partial-order/Pareto contract, not a weighted score. A creepage win
cannot buy a shorting regression.

## Survivors

### 1. Three bounded regional re-layouts

Treat each remaining cluster as a small floorplanning problem, moving the
whole local functional neighborhood and its copper together rather than one
component at a time:

- auxiliary-input/monitor region: `C14`, `U13`, and their immediately connected
  passives;
- gate-driver/bleeder/OVP region: `R4`, `U6`, `U16`, and their immediately
  connected passives;
- low-side-gate/RTD-fault region: `R23`, `R43`, and their immediately connected
  passives.

Use one baseline and at most two candidate layouts per region. A region that
cannot produce a Pareto improvement in two candidates is declared locally
infeasible; it does not receive more nudges.

**Why it survives:** it preserves local routing relationships and has a finite
stop condition. It attacks the failure observed in the discarded trial: moved
parts were separated from the copper and neighbors that constrain them.

### 2. Local isolation features, conditional on the lab answer

The five body-free pairs have unobstructed straight paths, so a deliberately
routed non-plated slot or board-edge notch may lengthen their surface path
without relocating either functional cluster. This becomes actionable only
after the certification lab determines how a closed slot end is treated under
Annex L / IEC 60664-1.

**Why it survives:** it changes the insulation geometry directly instead of
perturbing placement. It is currently blocked by a standards determination,
not by implementation difficulty.

### 3. Topology/package escalation for locally infeasible regions

If a regional experiment fails its two-candidate budget, stop placement work
and choose among a connector/interface relocation, a different package, an
isolated signal path, or a schematic partition change. This is especially
appropriate for K1↔R56, which is not one of the five body-free pairs and has
already been identified as needing package or topology work.

**Why it survives:** it changes the constraint that makes the layout
infeasible. It is more expensive, but unlike further nudging it can terminate.

### 4. Build a regional feasibility instrument before another board edit

Add a read-only evaluator that takes a named component set and candidate
placements, then reports the full acceptance vector: exact cross-domain pair
set, all DRC categories, courtyard collisions, and routed-pad endpoint drift.
It must compare sets, not only counts, and reject capped or misconfigured DRC
runs.

**Why it survives:** the discarded trial needed several independent commands
to reveal that it was worse overall. A single fail-closed report makes the
convergence contract cheap enough to use consistently.

**Implemented:** `scripts/evaluate_regional_layout.py`, with its acceptance
contract and routed-pad identity comparison owned by
`temper-quality-oracle/src/regional_feasibility.rs`.

## Rejected options

### Continue individual nudges

Rejected by direct falsification: five pairs went to zero while total DRC got
worse. There is no natural termination criterion and every move changes the
neighborhood for the next one.

### Optimize a weighted aggregate score

Rejected because weights allow safety categories to trade against each other.
A sufficiently large creepage weight can conceal a new short, exactly the
failure the complete DRC vector exposed.

### Re-run the global guard-corridor solve

Rejected as an incremental next step. The measured displacement floor makes
it a full-board redesign. It remains a product-level option, not a small safety
debt fix.

### Ratchet ceilings around the new layout

Rejected. DRC ceilings record an accepted measured board; they are not an
objective function and cannot legitimize an unexplained rise.

### Cut slots before the Annex L answer

Rejected because the closed-end treatment is the load-bearing standards fact.
Implementing first would convert an explicit unknown into fabricated safety
credit.

## Recommendation

1. Send the existing certification-lab inquiry now. Do not perform slot work
   until Question A is answered.
2. Build the read-only regional feasibility report.
3. Run the three regional experiments in descending shortfall order:
   `R23/R43`, `C14/U13`, then `R4/U6/U16`. Each gets at most two candidates and
   must satisfy the full Pareto contract.
4. Promote any region that fails both candidates to topology/package review.
5. Handle K1↔R56 directly as topology/package work, outside the five-pair
   placement burn-down.

## Definition of done

This work terminates when every currently actionable pair is in exactly one of
three states:

- cleared by a committed Pareto-improving regional layout;
- cleared by a lab-approved isolation feature;
- explicitly escalated with a named topology/package decision owner.

There is no fourth state called “try another nudge.”

## Sources

- `docs/evidence/2026-08-25-hv-selv-creepage-burndown-list.md`
- `docs/evidence/2026-08-26-c27-counterpart-creepage-move.md`
- `docs/plans/2026-08-01-002-feat-isolation-barrier-feasibility-experiment-plan.md`
- `docs/plans/2026-08-01-003-feat-mains-selv-isolation-barrier-rescope-plan.md`
- `docs/cert-lab-inquiry-final-2026-08-16.md`
