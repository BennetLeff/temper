---
artifact_contract: ce-unified-plan/v1
artifact_readiness: requirements-only
product_contract_source: ce-brainstorm
date: 2026-08-01
plan_type: experiment
---

# Isolation-Barrier Corridor-Feasibility Probe — Plan

## Goal Capsule

**Objective:** Empirically de-risk the isolation-barrier floorplan re-solve
(`docs/plans/2026-08-01-001-feat-mains-selv-isolation-barrier-plan.md`) by running
the CP-SAT corridor-constrained placement on the production board and determining
whether a feasible placement exists within a displacement budget — so the owner
commits to (or re-scopes) the floorplan work on evidence, not geometry heuristics.

**Product authority:** repo owner (accepts the GO/NO-GO decision record).

**Open blockers:** none — the placer machinery accepts the corridor constraint
(`solve_placement(isolation_barrier={...})`); the displacement-budget constraint
may require a small encoder addition, scoped as part of the experiment's
implementation.

## Product Contract

### Problem

The barrier plan's recommended path (domain-first floorplan re-solve) rests on the
assumption that a corridor-constrained placement is *solver-feasible* on the
production board within a tolerable component displacement. Static geometry says
~52–78 movers / 127–135 mm max drift is required, but that is a geometric bound,
not a solved placement. The experiment replaces the assumption with a measured
outcome.

### Scope (in)

- Run the corridor-constrained CP-SAT solve on the production netlist at
  **8.0 mm** corridor width, in **both orientations** (X vertical / Y horizontal).
- **Stage 1 (unconstrained):** is *any* feasible corridor placement achievable?
- **Stage 2 (budget-as-constraint):** is a feasible placement achievable with
  **max single-component displacement ≤ 25 mm**?
- **K3-relaxed variant** of both stages: run the same solves with the isolator
  straddle requirement dropped for **K3** (the one isolator whose pad clusters
  overlap by −0.5 mm), to quantify what the isolator-BOM phase unlocks.
- A written **decision record**: per-orientation GO/NO-GO for stages 1 and 2,
  the displacement numbers, and the K3-relaxed delta.

### Scope (out)

- Authoring the `MAINS_SELV_ISOLATION_BARRIER` keepout on the board.
- Routing after re-placement.
- DRC-ceiling re-measurement.
- Executing the floorplan re-solve as a delivered placement.
- The K3 BOM/footprint change itself.

### Success criteria

PASS = **stage 1 feasible in ≥1 orientation** AND **stage 2 within-budget feasible
in ≥1 orientation** (in the as-is model, or in the K3-relaxed model with the
K3-delta quantified).

A stage-1 NO in both orientations, even K3-relaxed, is a NO-GO that forces the
barrier plan to be re-scoped before any keepout is authored.

### Acceptance examples

- G1. Stage-1 solve, orientation X, as-is: returns feasible OR reports
  infeasible with the offending constraint named (expected: isolator straddle —
  this confirms K3 is the blocker).
- G2. Stage-1 solve, orientation X, K3-relaxed: returns feasible (expected) with
  a displacement distribution recorded.
- G3. Stage-2 solve, orientation Y, K3-relaxed, ≤25 mm budget: feasible (PASS
  signal) OR infeasible, in which case the max-displacement witness is reported.
- G4. Decision record states, per (orientation × variant × stage): feasible?,
  max displacement, total displacement, movers, and the K3-relaxed delta.

### Key decisions (settled)

- Probe width **8.0 mm** (the gate floor; widen after the isolator phase).
- **Staged design** (unconstrained first, then budget-as-constraint) so the
  experiment answers both "is it possible" and "is it within budget".
- **Both variants** (as-is + K3-relaxed) so the K3 prerequisite is quantified,
  not assumed.
- Displacement is measured vs current `pcb/temper.kicad_pcb` component positions
  (in-board pads only; staged parts such as C27 are excluded, matching the gate).

### Outstanding questions

- OQ-A. **Budget threshold:** the 25 mm/component figure is the default; if the
  owner wants a different tolerance (e.g. 20 mm), state it before execution.
- OQ-B. **Solve objective:** when unconstrained, what should the solver optimize
  (wirelength? displacement? existing default)? The stage-2 constraint supersedes
  this for the budget answer, but stage-1's displacement number depends on it.

## Sources / Research

- `packages/temper-placer/src/temper_placer/placer/cp_sat/isolation_barrier.py` —
  the HARD corridor constraint, isolator straddle feasibility, orientation/width
  kwargs; references a prior corridor-width control experiment.
- `packages/temper-placer/src/temper_placer/placer/cp_sat/_encoder_solve.py` —
  `solve_placement(isolation_barrier={...})` entry point.
- `docs/evidence/2026-08-01-isolation-barrier-feasibility.md` — the geometric
  baseline this experiment replaces with measured outcomes (52/78 movers,
  127/135 mm max drift, K3 −0.5 mm gap).
- `docs/plans/2026-08-01-001-feat-mains-selv-isolation-barrier-plan.md` — the
  plan this experiment de-risks.
