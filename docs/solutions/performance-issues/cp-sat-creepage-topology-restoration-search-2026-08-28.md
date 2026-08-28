---
title: "Dense creepage restoration is a topology-search problem, not a neighbour-query problem"
date: "2026-08-28"
category: performance-issues
module: temper_placer
problem_type: solver_search
component: cp_sat_placement
severity: high
applies_when:
  - "restoring the generated component-pair creepage matrix to the production CP-SAT placement model"
  - "considering spatial indexing, lazy cuts, displacement bounds, or UNSAT cores to reduce creepage search"
  - "a stripped creepage placement and a creepage-omitted production placement are each feasible, but their combined model returns unknown"
tags:
  - cp-sat
  - creepage
  - topology
  - lazy-constraints
  - displacement-bounds
  - unsat-core
  - deletion-testing
---

# Dense creepage restoration is a topology-search problem, not a neighbour-query problem

The Temper production board has 168 components and 9,176 non-zero
component-pair creepage requirements. The distribution is:

| required gap | pair count |
|---:|---:|
| 0.15 mm | 112 |
| 0.5 mm | 2,112 |
| 2.0 mm | 165 |
| 6.0 mm | 452 |
| 10.0 mm | 134 |
| 12.6 mm | 6,201 |

The apparent quadratic pair count is not the main performance problem.
Verification can use spatial indexing, and the complete pair graph compresses
to 11 exact Rust weighted-twin classes. The difficult operation is choosing a
globally consistent placement topology: for each enforced pair, CP-SAT must
choose whether one rectangle lies left, right, above, or below the other while
also satisfying the ordinary production model.

## What is known to be feasible

Two simpler models independently solve:

1. The stripped model containing board bounds, component rectangles, and all
   9,176 exact creepage requirements solves and passes the exhaustive Rust
   verifier in roughly 6--9 seconds.
2. The ordinary production model with generated creepage diagnostically
   omitted solves optimally in roughly 31--34 seconds.

Therefore neither the creepage geometry nor the ordinary production model is
independently impossible. The unresolved problem is restoring both while
retaining a useful global topology.

## Measurements that located the search wall

Restoring exact requirements by distance tier showed that every tier through
10 mm remains tractable. The final 12.6 mm tier is the first wall:

| cumulative stage | outcome | representative time |
|---|---|---:|
| production baseline, generated creepage omitted | optimal | 33.8 s |
| through 0.15 mm | optimal | 32.8 s |
| through 0.5 mm | optimal | 33.5 s |
| through 2 mm | optimal | 33.4 s |
| through 6 mm | optimal | 34.7 s |
| through 10 mm | optimal | 31--37 s |
| add all 6,201 pairs at 12.6 mm | unknown | 45--90 s |

A solution with all requirements through 10 mm enabled had only 300 current
12.6 mm violations, despite 6,201 possible pairs in that tier. This motivated
lazy and spatially batched restoration.

## Why local cut discovery did not converge

Adding only currently violated pairs kept each production solve fast, but the
violations moved when the solver rearranged the board:

| round | active exact rules | remaining violations |
|---:|---:|---:|
| 0 | 2,975 | 300 |
| 1 | 3,275 | 254 |
| 2 | 3,527 | 217 |

A Rust spatial-neighbour batcher added nearby alternatives around both
endpoints of each violation. It did not materially improve convergence:

| strategy | active rules | violations after the next solve |
|---|---:|---:|
| direct violated-pair cuts | 3,275 | 254 |
| 6 mm endpoint neighbourhood | 3,294 | 257 |
| 12 mm endpoint neighbourhood | 3,434 | 260 |

The index answered which components were close in the current placement. It
could not predict which pairs would become close after a global rearrangement.
This is why a quadtree improves verification cost but does not remove the
topology search.

## Why rigid topology encodings also failed

Several attempts compressed or preserved too much structure:

- Packing each of the 11 weighted-twin classes into one rectangular territory
  proved infeasible almost immediately. The rectangle envelopes were stronger
  than the original pairwise rules.
- Freezing all 9,176 pair-separation directions from the committed placement
  proved infeasible, both with and without coarse envelopes. The committed
  topology cannot simply be translated into legality.
- A conflict-focused repair frontier with 41 movable components proved
  infeasible; expanding it to 128 movable components returned unknown.

These results do not disprove hierarchy. They show that the useful hierarchy
must preserve coarse topology without imposing one solid rectangle or one
fixed direction for every pair.

## Safe-placement displacement experiment

The next experiment began from the fully verified stripped placement and
bounded every production component's Manhattan displacement:

```text
|x - safe_x| + |y - safe_y| <= radius
```

The hard bound was separated from the existing minimum-displacement objective
so the measurement did not conflate restriction with optimization.

| uniform radius | outcome | limit/time |
|---:|---|---:|
| 2 mm | proven infeasible | 18 s |
| 5 mm | unknown, no incumbent | 55 s |
| 10 mm | unknown, no incumbent | 55 s |
| 20 mm | unknown, no incumbent | 55 s |
| 40 mm | unknown, no incumbent | 55 s |

The definite result is narrow but important: the ordinary production model
cannot coexist with this safe stripped topology if every component moves by at
most 2 mm. Larger radii were unresolved, not proven infeasible.

## Why assumption-core extraction was the wrong instrument

Per-component displacement assumptions were added to identify which leashes
caused the 2 mm contradiction. Reifying the bounds changed solver propagation
enough to destroy the previously fast proof:

| displacement-bound form | outcome |
|---|---|
| unconditional bounds | infeasible in 18 s |
| 168 individual assumption literals | unknown after 70 s |
| 11 shared weighted-twin literals | unknown after 90 s |
| one shared literal for all 168 bounds | unknown after 90 s |

The one-literal control is decisive: assumption count and grouping quality are
not the cause. A conditional/reified version of these geometric bounds is a
substantially weaker search instrument than fresh unconditional constraints.
Do not infer implicated components from an empty core or an `unknown` result.

## The resulting rule

Use fresh-model deletion tests for displacement diagnosis. Do not place the
movement bounds behind assumption literals on this production model.

A deletion test retains unconditional constraints and varies only which
components receive the narrow radius:

```text
baseline: every component radius = 2 mm
test G:   members of group G radius = 40 mm; all others = 2 mm
```

Interpret results in three states:

- **infeasible**: releasing that group was insufficient;
- **feasible**: releasing that group was sufficient for production
  feasibility, after which exhaustive Rust creepage verification is required;
- **unknown/timeout**: no conclusion.

Deletion testing costs more solver runs, but each model retains the strong
unconditional formulation that produced the only useful proof. Runs are
independent, bounded, cacheable, and parallelizable.

## Recommended deletion-testing design

Start with the 11 Rust weighted-twin groups, but treat them only as an initial
partition rather than as physical territories.

1. Reproduce the all-2-mm infeasible baseline with unconditional bounds.
2. Independently widen each one of the 11 groups to 40 mm.
3. Record solver status, elapsed time, released members, and—only for complete
   candidates—the exhaustive Rust creepage violation count.
4. If one group is sufficient, split it deterministically and retest its
   children.
5. If every singleton group release remains infeasible, test balanced halves
   and then combinations; this detects blockers spanning multiple groups.
6. Never treat `unknown` as evidence that a group matters or does not matter.
7. Cache each test by the canonical released-ref set, radius vector, board
   hash, and production-option digest.

The immediate goal is explanatory, not a board rewrite: identify the smallest
released component set known to change the unconditional 2 mm result, and the
remaining exact creepage violations in any production-feasible candidate.

### First deletion matrix (measured 2026-08-28)

The first implementation used the 11 weighted-twin groups, a 2 mm base
radius, a 40 mm released-group radius, and a 25-second external limit per
fresh model. The unconditional baseline reproduced the useful proof in
17.453 seconds. Four singleton releases were also proven insufficient:

| released group | members | outcome | time |
|---|---:|---|---:|
| none (baseline) | 0 | infeasible | 17.453 s |
| twin 01 | 14 | infeasible | 18.795 s |
| twin 06 | 4 | infeasible | 22.679 s |
| twin 08 | 2 | infeasible | 21.741 s |
| twin 10 | 8 | infeasible | 21.031 s |

The other seven singleton releases timed out at 25 seconds, including the
96-member class. No singleton produced a production-feasible candidate. The
campaign correctly did not schedule balanced-half tests: an `unknown` or
external timeout is not proof that a singleton release was insufficient.

This is useful negative evidence. The four proven groups cannot individually
explain the topology conflict, while the other seven remain candidates rather
than positives. The next measurement should spend larger budgets only on
those unresolved groups, or test deterministic multi-group releases that do
not rely on reified constraints.

## Implementation history

The investigation is represented by these branch commits:

- `dffe3ff9e` — exact distance-tier restoration;
- `1486a809f` — Rust spatial neighbourhood batching;
- `8dac729aa` — independent safe-topology radius sweep;
- `42b68d778` — per-component selective displacement-core diagnostics;
- `6468dae62` — Rust weighted-twin grouped-core diagnostics.

The grouped and individual core APIs remain useful for smaller models, but the
real-board measurements above prohibit using them as evidence for this
production displacement diagnosis.
