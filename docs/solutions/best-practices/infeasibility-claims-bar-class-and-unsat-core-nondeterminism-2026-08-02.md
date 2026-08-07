---
title: "Methodology: an 'infeasible' claim must name its bar class, and unsat cores are not a wall inventory"
date: 2026-08-02
category: best-practices
module: temper-placer
problem_type: methodology
component: placer
severity: high
applies_when:
  - "A solver reports infeasible and the unsat core is used to decide what to fix next"
  - "Two formulations of the 'same' solve (pinned vs repair, with-zones vs without) give different infeasibility stories"
  - "A feasibility claim must be qualified by which geometry the solver encoded (boxes, centers, zones) versus which geometry the acceptance gate measures (exact copper)"
  - "Deciding whether a follow-up effort (validator-aligned audit, copper-accurate constraint) can unlock a solve wall"
symptoms:
  - "The handoff's wall inventory said the unsat core named edge_margin_C1..C21; on the same base the same formulation produced a 1-entry core, a 15,736-entry core, and an empty core across runs"
  - "A scoped solve was reported 'infeasible, domain bar forces full re-layout', yet every one of the 45 pairs named by the direct measurement was copper-clean at the pinned positions (slack 0.6–16mm)"
  - "A pure-geometry FREE={K3} solve is optimal while the pinned FREE={K3,C27} + 12,022-constraint solve is infeasible, and both are true"
root_cause: measurement_precision
resolution_type: methodology
tags:
  - infeasibility-analysis
  - unsat-cores
  - box-vs-copper
  - solve-wall
---

# An "infeasible" claim must name its bar class; unsat cores are not a wall inventory

## Lesson 1: infeasibility is a property of the encoded bar, not the board

The scoped solve (FREE {K3,C27} + 12,022 domain-clearance + 530 keepaway +
fixed-copper) is infeasible. The repair recipe (nothing pinned, ≤60mm
displacement) is feasible **and its solved placement is validator-clean** (C27
on-board at (28.62, 222.0), all 271 K3/C27 pairs ≥ 8.0mm copper, worst 8.66mm,
zero new inter violations). Both statements are true of the same board.

The reconciliation is the bar class:

- The solver encodes **box separation** (component bbox, even-rounded integer
  grid, rotation-aware half-extents).
- The acceptance gate measures **exact copper-to-copper** (pad geometry, the
  validator).
- Measured on the production board, **45/45** of the pairs that make the pinned
  formulation infeasible are box-violating but **copper-clean** at the pinned
  positions (slack 0.6mm C23/R17 to 16mm L1 pairs) — the box bar is strictly
  stricter than the copper bar on every pair that matters.

A "no placement exists" claim must therefore be written
"no placement exists **under the box bar with this pin set**". The qualifying
clause is not decoration: it decides whether a validator-aligned effort can
unlock the wall (here: the premise holds mechanically — a copper-accurate
constraint would accept the pinned board — but the wall's actual cause was the
**pin set**: C27's 43×23mm box has no on-board spot with everything else pinned,
even in pure geometry).

## Lesson 2: unsat cores are non-minimal and search-order-dependent

CP-SAT's `SufficientAssumptionsForInfeasibility` is not a minimal core and
depends on search order. The same formulation measured:

- a 1-entry core (`edge_margin_C27`),
- a 15,736-entry core (all 169 edge refs + all separation pairs),
- an empty core,

across runs. The deterministic wall inventory must be derived by **direct
measurement**: evaluate every encoded constraint's value at the pinned positions
and collect the violators (45 pairs: 44 domain @8.0/1.0 + 1 keepaway). That set
reproduces; core contents do not.

## Lesson 3: pin set and bar class are the two levers; change one at a time

The wall analysis then decomposes cleanly:

| formulation | pin set | bar | result |
|---|---|---|---|
| scoped solve | FREE {K3,C27} | box + zones + fixed-copper | infeasible (C27 footprint vs packed board) |
| pure-geometry FREE={K3} | FREE {K3} | box only | optimal, K3 unmoved |
| repair recipe | nothing pinned, ≤60mm | box + zones + fixed-copper | feasible, validator-clean |
| repair with zones (run-C) | nothing pinned, ≤60mm | box + **zones** + fixed-copper | infeasible, core names edge-margin refs again |

The zones variant resurrects edge-margin constraints in the core (the edge-margin
wall was paid down for the pinned formulation by #568/#579, not for the
zone-constrained repair path) — another demonstration that the core inventory
must be re-derived per formulation, and that "wall paid down" is formulation-local.

## The recipe

1. Reproduce the infeasibility; record the formulation (pin set, bar, zones,
   fixed-copper flags) — the claim is meaningless without it.
2. Do not quote the unsat core as a wall inventory; use it as a hint, then
   re-derive the violation set by direct constraint evaluation at the pinned
   positions.
3. For each named pair, measure both bars: box distance (exact solver geometry)
   and exact copper distance (the validator's model). Classify: box-violating +
   copper-clean → bar-approximation-strict (a validator-aligned effort can
   accept it); both violating → genuine geometry (only a move, slot, or
   re-layout fixes it).
4. Separate the levers: pin set vs bar class vs zones. Feasibility claims and
   wall fixes must say which one they changed.

## Evidence

- `docs/evidence/2026-08-01-solve-wall-box-vs-copper-gap.md` — 45/45 pair table,
  bar-class measurement, repair-recipe validator-clean placement.
- `docs/evidence/2026-08-01-gap1-runC-unsat-core.md` — the zones-variant core,
  edge-margin resurrection, run-C analysis.
- `docs/evidence/2026-07-31-pd2-clearance-resolve.md` — the PD2/8.0 re-solve that
  cleared the placement-fixable inter pairs.
