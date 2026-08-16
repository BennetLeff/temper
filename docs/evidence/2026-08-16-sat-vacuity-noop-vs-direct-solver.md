---
title: Stage 3 SAT capacity vacuity — no-op is byte-identical to the merged direct solver
type: evidence
date: 2026-08-16
topic: router-stage3-vacuity
status: measured
---

# Stage 3 SAT capacity vacuity — root cause, and the no-op equivalence proof

**Branch:** `fix/sat-vacuity-connectivity-constraint` (worktree
`/tmp/opencode/agent-sat-vacuity-v2`), based on `origin/main @ 7b424488f`
(#1260 direct solver merged).
**Board:** `pcb/temper.kicad_pcb` byte-identical to `origin/main`,
**never modified** by this work.

## The vacuity, confirmed at source

The Stage 3 SAT model (`temper-design-bundle/src/model_builder.rs` +
`temper-rust-router-core/src/encoding.rs`) creates one `NetChannelVar`
(`uses_{net}_{channel}` boolean) per (net, skeleton-edge) pair — 22.5M
variables at the current 204K-edge skeleton — and **nothing in the model
ever forces any of them true**:

| constraint | semantics | forces a NetChannelVar true? |
|---|---|---|
| `Capacity` | `AtMostK` (Sinz sequential counter), upper bound only | **no** — "at most K true" is satisfied by all-false |
| `DiffPair` | biconditional p↔n | **no** — satisfied by both-false |
| `LayerConstraint` | `allowed: false` unit clauses only | **no** — forbids, never requires |
| `ChannelSeparationConstraint` | never instantiated in production | — |
| `_apply_pcl_constraints` | no-op under net-batching | — |

The all-`false` assignment is therefore *always* a satisfying model — every
recorded solve returns "0 conflicts, 0 decisions" and an EMPTY topology
(measured 0/30 nets with non-empty `uses_channels`,
`docs/brainstorms/2026-08-12-sat-capacity-vacuity-options.md` §1.2). Stage 3
has never decided topology; Stage 4's occupancy-grid A* does the entire job
from raw pad positions. The monolithic CNF additionally cannot fit on this
machine: 110 nets × 204,144 edges = ~22.5M primary vars → ~182-200 GB
demand, OOM-killed at ~58 GB (`docs/evidence/2026-08-15-stage3-memory-
blowup-investigation.md`).

## Two fixes measured — the merged direct solver and the no-op converge

Main fixed the vacuity by merging the direct capacity-aware solver (#1260):
Stage 3 now computes real per-net channel paths and the 200 GB monolith is
gone. This branch implements the task dispatch's option (d) instead: make
Stage 3 a structural no-op (empty `Stage3Output`), keeping SAT/direct
reachable via `--net-batching`, `enable_bundling`, or
`TEMPER_STAGE3_FORCE_SAT=1`.

**The measured result is that both fixes produce byte-identical routed
boards.**

### Production board `pcb/temper.kicad_pcb` @ 7b424488f (monolithic, no net-batching)

| configuration | wall | Stage 3 RSS | pad-connected | segments/vias/zones |
|---|---|---|---|---|
| merged direct solver (#1260 default) | 242.2 s | ~0 (no CNF) | **88/139** | 5603 / 155 / 59 |
| **no-op (this branch)** | 243.6 s | ~0 (no CNF) | **88/139** | 5603 / 155 / 59 |

Both routed boards are **byte-identical** (md5 `8782cce29a0…`), including
the `NetRouteResult` verdicts (88 connected, 6 zone-dependent, 7 partial,
38 failed) and the fake-completion / honest-gap split (7/44). The direct
solver's topology guidance changed nothing about Stage 4's output on this
board.

### Fixture `temper_fixture_33.kicad_pcb` (route_pcb settings, zone pours on)

| configuration | completion | unrouted | segments | unexplained copper gap |
|---|---|---|---|---|
| merged direct solver (#1260 default) | 0.69 | 8 | 3533 | [] |
| **no-op (this branch)** | 0.69 | 8 | 3533 | [] |

Byte-identical here too — and notably the merged direct solver emits **zero
topology** on the fixture (`topology_solved_nets == []`), so both routes are
pure Stage-4 fallback A*. (An earlier measurement of 0.54/5-gaps against
the direct solver was taken with a **stale pre-#1260 `.so`** and is
retracted; the merged code with its pad-waypoint/turn-only subsampling
fixes does not regress the fixture.)

## Why this matters

The vacuity is real and was costing 182-200 GB. Main's #1260 fix removes
that cost. This branch shows the *same* route quality is achievable with
strictly less machinery: a no-op Stage 3 (with the SAT/direct paths kept
reachable for regression) routes the board byte-for-byte identically to the
merged direct solver, in the same wall time. The choice between the two is
not a route-quality decision — the measured evidence says they are
equivalent on this board — it is a YAGNI / maintainability decision, which
is an owner call.

## Wiring (this branch)

`_pipeline_route.py::_run_stage3` — the monolithic (non-net-batching,
non-bundling, non-forced) path returns an empty `Stage3Output` immediately.
SAT and direct-solver paths remain fully reachable and unchanged:
`--net-batching` (the measured 92/139-era reference recipe),
`enable_bundling`, and `TEMPER_STAGE3_FORCE_SAT=1`. The auto-batch safety
net (`_AUTO_BATCH_VAR_THRESHOLD`, #1250) guards only those remaining
model-building paths; its tests reach the SAT machinery through the escape
hatch.

## Tests updated to the new contract

- `test_stage3_direct_solver.py` dispatch tests: default is the no-op
  (empty Stage3Output, no ModelBuilder, no direct call); the escape hatch
  still reaches the SAT path; net-batching still takes priority; the
  direct solver's post-condition audit is pinned via `_run_stage3_direct`.
- `test_stage3_auto_batch.py`: default (any size) is the no-op — the
  auto-batch net cannot and must not fire on it; it still guards the
  FORCE_SAT path.
- `test_adapter.py` pruning-wiring: default path builds no ModelBuilder;
  the SAT path (via the escape hatch) still receives
  `enable_geographic_pruning`.
- `test_topology_copper_audit.py` full-pipeline test: default Stage 3
  claims no topology (`topology_solved_nets == []`); the audit's
  anti-vacuity role is exercised by the synthetic tests in the same module.

## What this does NOT claim

- It does not claim the direct solver is wrong — only that on the measured
  boards its output is byte-identical to a no-op, so the route-quality
  argument does not prefer either fix.
- It does not touch net-batching, placement, Stage 4's A*, or the
  `clearance`/`creepage` DRC picture.
- It does not claim Stage 3 can never be useful: a future stage whose
  topology guidance measurably improves Stage 4's output (beyond the
  byte-identical equivalence measured here) would need its own
  connectivity-forcing design and its own route-quality validation against
  this no-op baseline.
