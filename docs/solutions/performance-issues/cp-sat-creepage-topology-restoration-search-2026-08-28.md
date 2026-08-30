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

The other seven singleton releases initially timed out at 25 seconds. A
targeted fresh-instrument rerun at up to 60 seconds resolved all seven as
infeasible; the actual proofs completed in 5.739--11.092 seconds. Thus every
one of the 11 weighted-twin singleton releases is proven insufficient,
including the 96-member class. The discrepancy in wall time reinforces the
rule that solver timeout is not evidence and that measurements must preserve
their exact environment and status.

The deterministic member-balanced split then had one already-tested half:
the 96-member `twin_02` class. Its 72-member complement was unresolved after
both 60 and 120 seconds. Releasing all 168 components to 40 mm also exceeded
an external 120-second limit without an incumbent. Neither result is an
infeasibility claim, and neither candidate reached the Rust verifier.

The canonical machine-readable frontier is stored at
`docs/evidence/2026-08-28-displacement-deletion-frontier.json`, keyed by the
board SHA-256, exact released refs, radii, and production options. It records:

- the proven all-2-mm baseline;
- all 11 proven-insufficient singleton releases;
- the unresolved 72-component balanced complement; and
- the timed-out all-168 upper-control release.

This is the bounded search frontier: there is no known sufficient release set
within the completed probes. Cross-half combinations are not justified by the
planner because the 72-component half is unresolved rather than proven
insufficient.

## Decision after deletion testing

Deletion testing answered the component-local hypothesis. The 2 mm conflict
is not repaired by releasing any one weighted-twin class, including the class
containing 96 of the 168 components. More combinations would be expensive and
hard to interpret while the 72-component half and the all-released control are
still unresolved.

The next search should therefore change axes. Instead of asking *which
components may move farther?*, ask *which production constraint family first
makes the known-safe creepage topology infeasible or intractable?*

This distinction matters because releasing all 168 displacement bounds does
not remove production constraints. The 120-second all-released timeout is
consistent with at least three different causes:

1. the complete combined model is feasible but has weak propagation;
2. one production constraint family contradicts the safe topology; or
3. two individually compatible families interact to create the conflict.

The deletion frontier cannot distinguish those cases. A constraint-family
feasibility ladder can.

## Next experiment: independent constraint-family probes

Build each probe from a fresh model. Use the stripped, exhaustively verified
creepage model as the common base, then add production constraint families in
a declared deterministic order. Do not infer causality from a single
cumulative order alone: after the first cumulative failure, also test that
family independently on the base and test the previously accepted prefix
without it.

Every probe must record four states separately:

- **accepted**: a complete placement exists; run the exhaustive Rust creepage
  verifier before calling the combined candidate clean;
- **infeasible**: the exact fresh model was proven contradictory;
- **unknown/timeout**: the solver did not decide within the bound;
- **invalid/error**: the experiment itself was malformed or failed.

The first bounded campaign should be diagnostic rather than exhaustive:

1. Reproduce the stripped creepage base.
2. Probe each available production family independently against that base.
3. Run a cumulative ladder in a stable, documented order, carrying only an
   accepted placement as the next hint.
4. At the first non-accepted cumulative stage, run leave-one-out probes over
   the active prefix.
5. If every family is independently accepted but a prefix fails, bisect the
   interacting family set with fresh models; do not weaken any family.
6. Persist a canonical frontier keyed by board hash, exact family set,
   production-option digest, and limits so interrupted runs can resume.

The desired output is not merely "the full model timed out." It is the
smallest evidence-backed set of production families known to change the safe
creepage base from accepted to infeasible or unresolved. That set determines
whether the next engineering work is a correctness fix, a stronger Rust-owned
encoding, or a more targeted search decomposition.

### Implemented diagnostic harness

The family-ladder harness now consists of three deliberately separate parts:

- `constraint_family_probe_planner.py` plans independent, cumulative,
  leave-one-out, and interaction-bisection probes from recorded evidence;
- `constraint_family_campaign.py` runs each exact family set in a fresh child
  process, verifies complete candidates, and permits hints only from accepted
  placements; and
- `constraint_family_frontier.py` persists canonical resumable results keyed
  by board identity, exact family set, stable option digests, and solve limits.

A dynamically planned campaign always runs the empty-family base first. If
that control is not accepted, the planner is not invoked. Optional production
families still require their real caller-owned artifacts; the harness refuses
to synthesize a manifest or treat an empty placeholder as a measurement.

### First authoritative family frontier (measured 2026-08-28)

The production adapter found three families with complete live inputs on this
checkout: exact generated creepage, tank creepage, and the F.Fab body-collision
audit. The validator audit was unavailable because `elec/build/default.net`
had not been generated. Repair-only families were reported unavailable rather
than represented by empty options.

With a Rust-verified stripped warm start and a 45-second per-probe limit:

| exact family set | solver outcome | time | exhaustive creepage result |
|---|---|---:|---|
| none | optimal | 36.588 s | 1 violation |
| exact creepage | unknown | 45.051 s | no candidate |
| tank creepage | optimal | 26.761 s | 1 violation |
| body-collision audit | error/rejected | 36.014 s | candidate rejected by audit |

A targeted fresh exact-creepage probe remained `unknown` after 120.078
seconds. The canonical five-record frontier, including both exact-creepage
budgets, is `docs/evidence/2026-08-28-constraint-family-frontier.json`.

The body-collision row needs careful interpretation. This family is a
post-solve acceptance oracle, not a propagating CP-SAT constraint. It rejected
an otherwise optimal candidate for 14 new F.Fab collisions (worst:
`C27`--`L1`, 493.875 mm²). That is evidence that the candidate is physically
unacceptable, but not a proof that no collision-clean placement exists.

The family ladder therefore confirms the earlier distance-tier result with a
different instrument: exact generated creepage is the available encoded
family that changes a quickly solvable production baseline into unresolved
search. Tank creepage is not that wall. The next solver work should focus on
the 12.6 mm exact-creepage topology encoding or on generating a collision-safe
candidate during search; further component-deletion combinations have lower
diagnostic value.

### Baseline violation replay and topology-hint controls

Replaying the accepted empty-family placement through the same production
adapter and Rust stripped verifier identified its sole exact violation:

| pair | required | actual | best direction in candidate |
|---|---:|---:|---|
| `C1`--`C13` | 12.6 mm | 10.1 mm | `C13` below `C1` |

The alternative horizontal gap was only 6.0 mm. `C1` is a 7.5 x 18.5 mm
through-hole capacitor and has 134 neighbours in the 12.6 mm graph; `C13` is
a 1.46 x 2.96 mm SMD capacitor with 48 such neighbours. The 2.5 mm local
shortfall therefore looked like a useful first topology seed, but two bounded
controls falsified that interpretation:

1. Starting the sound lazy-cut path from the accepted placement ran three
   feasible verifier rounds, then returned `unknown` after 117.633 seconds.
   Its last complete candidate had 222 exact violations. Repairing the one
   visible pair caused a global topology jump rather than local convergence.
2. A temporary implementation seeded all four separation literals for every
   encoded `SeparatedConstraint` from the complete Rust-verified stripped
   placement (exactly one true direction per pair). These were `AddHint`
   values, never hard equalities. The full exact-creepage production model
   still returned `unknown` with no incumbent after 120.017 seconds, matching
   the previous 120-second control. The implementation was removed after the
   negative measurement rather than retained as an unproven optimization.

Both measurements ran after all ten pyo3 extension freshness checks passed.
They narrow the next encoding experiment: neither one violated pair nor 9,176
independent Boolean direction hints supplies the missing propagation. The
next candidate should encode a sparse set of shared ordering relations for the
6,201-pair 12.6 mm tier and measure presolve/branching plus first-incumbent
time. Independent per-pair hints should not be repeated.

### Designer-declared corridor comparison

The next bounded probe encoded one hard, movable 12.6 mm box corridor between
the explicit 40-member HV-only bucket and 110-member SELV-only bucket. The
eight isolators and ten unclassified components remained outside the corridor
relation. Vertical and horizontal axes ran as independent fresh models with
the same Rust-verified stripped hint and separate 120-second CP-SAT budgets.

Both restricted models produced optimal complete candidates, unlike the
unrestricted exact-production control that had returned `unknown` with no
incumbent at 120 seconds:

| axis | first incumbent | solver wall time | conflicts | branches | presolved variables / constraints | result |
|---|---:|---:|---:|---:|---:|---|
| vertical (`x`) | 60.492 s | 60.503 s | 4,450 | 352,480 | 69,254 / 70,492 | optimal, rejected |
| horizontal (`y`) | 59.667 s | 59.678 s | 6,484 | 331,259 | 69,254 / 70,492 | optimal, rejected |

The corridor therefore supplied the missing global propagation, but neither
candidate passed the required post-solve geometry gates:

| axis | exhaustive Rust creepage | REQ-SAFE-01 | F.Fab |
|---|---|---|---|
| `x` | 1 violation: `J1`--`R27`, 0.495 / 0.5 mm | trusted geometry; 94 hard records, 0 coverage gaps, 3 intra-footprint findings | 14 disallowed collisions |
| `y` | 1 violation: `C1`--`PS1`, 12.595 / 12.6 mm | trusted geometry; 100 hard records, 0 coverage gaps, 3 intra-footprint findings | 14 disallowed collisions |

The strongest supported conclusion is narrow: a designer-declared shared
ordering can turn this search from no incumbent into an optimal candidate
inside the existing bound, but this particular HV-low/SELV-high corridor does
not produce an acceptable board placement. The tiny exhaustive-creepage
shortfalls are still real gate failures; they were not rounded away or
reclassified. The much larger validator and body-collision failures show that
the corridor is only a topology aid, not a substitute for copper-aware or
body-aware search structure. Do not promote it to a production configuration
surface from this result.

The canonical comparison is stored at
`docs/evidence/2026-08-28-creepage-search-corridor-experiment.json`. Its input
identity records all 9,176 exact requirements (including 6,201 at 12.6 mm),
the four domain buckets, solver settings, source hashes, complete candidates,
telemetry, and independent gate censuses. All ten pyo3 extensions passed the
freshness gate immediately before measurement.

### Collision-aware corridor follow-up (measured 2026-08-30)

The bounded collision-cut comparison is recorded at
`docs/evidence/2026-08-30-collision-aware-creepage-corridor.json`. It used
seed 0, four CP-SAT workers, the same 9,176-requirement identity, and a
four-round campaign budget of 120 seconds per axis (480 seconds total). The
extension freshness gate passed for all 10 pyo3 modules immediately before
the measurement, and the PCB SHA-256 was unchanged before and after.

The historical unrestricted 120-second control returned `unknown` without
an incumbent. The matched unrestricted control returned an optimal candidate
after about 123 seconds, but it failed exact creepage and the acceptance
instrumentation (REQ-SAFE-01 input was unavailable and F.Fab coverage was
incomplete). Both collision-aware axes stopped during fail-closed preparation:
the board has no complete F.Fab body coverage for ten expected references
(`F1`, `J1`, `L2`, `R30`, `RT1`, `TP1`--`TP4`, and `U27`), and
`elec/build/default.net` is absent for REQ-SAFE-01. No solver round or cut was
claimed for either axis. These axis results are classified as insufficient
evidence, not non-convergence, because the required complete candidate and
sound applied-cut preconditions were not exercised.

This follow-up therefore does not establish collision-cut convergence or
physical acceptance. It preserves the earlier conclusion: the corridor is a
search-topology aid, while a production acceptance result requires complete
independent creepage, REQ-SAFE-01, and exact F.Fab evidence in the same regime.

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
