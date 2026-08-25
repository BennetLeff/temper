<!-- provenance: commit=7b424488fc70f86b3be0630b9b213e38313df4a2 dirty=UNKNOWN -->
---
title: Stage 3 SAT capacity vacuity — the fix (direct capacity-aware topology solver)
type: evidence
date: 2026-08-16
topic: router-stage3-vacuity
status: measured
---

# Stage 3 SAT capacity vacuity — the fix

**Branch:** `fix/stage3-sat-capacity-vacuity-fix` (worktree
`/tmp/opencode/agent-sat-vacuity-fix`), base `origin/main @ 5cebf30f0`.
**Board:** `pcb/temper.kicad_pcb` byte-identical to `origin/main`,
**never modified** by this work (sha256 verified before/after).

## What was vacuous, stated first

The Stage 3 SAT model (`temper-design-bundle/src/model_builder.rs` +
`temper-rust-router-core/src/encoding.rs`) creates one
`NetChannelVar` (a `uses_{net}_{channel}` boolean) per (net, skeleton-edge)
pair — 22.5M variables at the current 204K-edge skeleton — and **nothing in
the model ever forces any of them true**:

| constraint | semantics | forces a NetChannelVar true? |
|---|---|---|
| `Capacity` | `AtMostK` (Sinz sequential counter), upper bound only | **no** — "at most K true" is satisfied by all-false |
| `DiffPair` | biconditional p↔n | **no** — satisfied by both-false |
| `LayerConstraint` | `allowed: false` unit clauses only (`model_builder.rs` `create_layer_constraints`) | **no** — forbids, never requires |
| `ChannelSeparationConstraint` | never instantiated anywhere in production | — |
| `_apply_pcl_constraints` | no-op under net-batching (`_solve_subset` never passes `pcl_constraints`) | — |

The all-`false` assignment is therefore *always* a satisfying model. This is
not inference — it is what "0 conflicts, 0 decisions" has meant on every
recorded solve of this pipeline, and it was measured directly on
`docs/brainstorms/2026-08-12-sat-capacity-vacuity-options.md` §1.2: **0 of
30 nets across 3 batches had any non-empty `uses_channels`**. Stage 3 has
never decided topology; `extract_topology` (`extraction.rs`) parses only
solver-assigned-true variables, so the topology graph was empty for every
net in every configuration. Stage 4's occupancy-grid A* did the entire job
from raw pad positions.

Compounding the vacuity, the monolithic CNF cannot fit on this machine at
all: the Sinz `AtMostK` encoding over 204K channel-capacity constraints ×
110 nets multiplies 22.5M primary variables into ~399M CNF variables /
~768M clauses ≈ **182–200 GB demand** (`docs/evidence/2026-08-15-stage3-
memory-blowup-investigation.md`), all of it encoding constraints that
structurally cannot bind. The default `route_board.py` (monolithic, no
`--net-batching`) died at ~58 GB inside `encode_to_cnf` on every run.

## The fix

`temper-rust-router-core/src/direct_topology.rs` replaces the SAT encoding
with a **direct, capacity-aware, graph-based topology assignment**. It is
the task's sanctioned "algorithm replacement" (docs/plans/2026-08-12-003
Option E2's intent — make Stage 3 decide topology — computed directly
instead of encoded as clauses):

1. **Connectivity forcing, computed directly.** Each net's pads snap to the
   nearest skeleton node; a shortest path is computed between consecutive
   pads (multi-pad nets chain segments — a Steiner-tree approximation).
   Every routed net's `uses_channels` is therefore non-empty and connected
   by construction — the exact property the SAT model never forced.
2. **Capacity enforced by construction.** Edges whose remaining width
   cannot carry the net are *blocked* in the search (a capacity-aware
   Dijkstra), so later nets re-route around congested channels; a net whose
   path would exceed an edge's capacity is left unrouted and reported in
   `degraded_nets`, falling through to Stage 4's existing
   `fallback_channel_path` A* — the same honest degraded handling the
   net-batching path uses. Capacity semantics mirror the SAT model exactly:
   `usable = capacity × 0.8` (the model builder's `slack_factor`), and an
   edge with no recorded width carries no constraint.
3. **Per-traversal capacity accounting.** A net whose pads sit at a
   skeleton spur tip must traverse the spur edge twice (out-and-back). Each
   segment's capacity is committed *inside* the net's chain, so the second
   traversal sees the first's consumption — a spur that cannot carry
   `2×width` makes the net unrouted rather than over-committed. (This is
   *more* conservative than the SAT's `AtMostK`, which counts nets, not
   traversals, and would have silently under-counted the physical copper in
   the channel.)
4. **Post-conditions verified and raised on** (the direct analog of
   `audit_result`): every routed net's full path is a connected walk
   through the skeleton, every emitted channel is an edge of that path
   (no fabricated waypoints), and no capacity-constrained edge is
   over-committed (`remaining + committed == usable`). These checks
   caught three real bugs during development — a consecutive-duplicate
   dedupe that corrupted both bookkeeping and walk continuity, the
   per-traversal gate gap (a spur out-and-back could commit 2×width to an
   edge that only carries width), and an emitted-channel/walk mismatch
   after waypoint subsampling — and are standing checks, not scaffolding.
5. **Pad-waypoint emission.** The emitted `uses_channels` is one channel
   id per consecutive pad pair (topology-decided order — given order for
   2-pad nets, sorted for multi-pad, matching Stage 4's fallback
   convention), encoding the pads' own coordinates. Corridor waypoints
   were measured to *degrade* Stage 4 on this board (turn+junction:
   62/139 — see the corridor-waypoint finding below); the pads-only
   emission achieves batched parity (89/139) at 1/3 the wall time while
   the full capacity-aware path remains the recorded, verified decision.

The output shape is byte-compatible with `extraction::extract_topology`'s
`TopologyGraph` (same `uses_channels` / `path_graph` /
`total_length_estimate` fields, canonical channel ids generated by the same
`canonical_channel_edges` algorithm), so Stage 4's `map_topology_to_channels`
consumes it unchanged.

## Where it is wired

`_pipeline_route.py::_run_stage3` — the monolithic (non-net-batching) path
now dispatches to `_run_stage3_direct` →
`temper_rust_router.solve_topology_direct_py` (Rust). The SAT paths remain
fully reachable and unchanged: `--net-batching` (the measured 92/139
reference recipe), `enable_bundling`, and the new
`TEMPER_STAGE3_FORCE_SAT=1` environment escape hatch for
comparison/regression. `max_sat_nets` (selective cap) is honored by the
direct solver (only the selected nets receive topology; the rest fall to
Stage 4's fallback).

## Memory before/after (measured)

| configuration | Stage 3 peak RSS | outcome |
|---|---|---|
| monolith, before (2026-08-15) | ~58 GB observed → OOM-killed; 182–200 GB intrinsic demand | never completed |
| batched `--net-batching` (reference) | ~1–5 GB per batch subprocess | completes, but vacuous (empty topology) |
| **monolith, after this fix** | **Stage 3 adds ~0 GB over the Stage-2 baseline** (HWM 2.94 GB is Stage 2's EDT; Stage 3 RSS stayed at the pre-Stage-3 level through the direct solve) | **completes: 96/139 pad-connected in 291 s, peak RSS 2.94 GB** |

No CNF is built at all — the 22.5M-variable / 399M-aux / 768M-clause
encoding is gone.

## Route result (measured this task, current `main` tree)

`scripts/route_board.py --no-net-batching --output ...` (monolithic, the
direct solver):

| metric | monolithic (this fix) | batched reference (`--net-batching`) |
|---|---|---|
| wall | **318 s** | 956 s (same tree, same machine load) |
| peak RSS | **~2.9 GB** (Stage 2's EDT; Stage 3 adds ~0) | ~1–5 GB per batch subprocess |
| pad connectivity | **89/139** | 89/139 (same tree) |
| fake-completion | 11 | 13 |
| DRC on output | 1556 violations (503 clearance, 228 unconnected, 200 shorting) | — |

**Monolithic route completes in < 4 GB, no OOM — the primary deliverable.**
Connectivity is **equal to the batched reference (89/139) on the same
tree**, at **1/3 the wall time**, with the vacuity fixed (Stage 3 decides a
real capacity-aware topology; the batched SAT decides nothing — its 89 is
produced entirely by Stage 4's fallback A*). Earlier measurements on the
pre-rebase tree: 96/139 monolithic vs 92/139 batched (the reference's
92 → 89 drop is the intervening main-tree changes — board #1248, zone
generator #1257, stricter connectivity #1256 — which affected both arms
equally).

## The corridor-waypoint finding (measured, four iterations)

Emission granularity was iterated against the real board; the fourth
iteration is what shipped:

1. **Per-edge emission**: monolithic route still grinding at 3× batched
   wall time (25+ min) — Stage 4 A* routes waypoint-to-waypoint, and a
   200-edge net path means ~200 A* segment searches.
2. **Junction+turn subsampling** (degree≠2 kept): still grinding at 40
   min — a medial-axis skeleton's average degree is >2, so the junction
   rule keeps almost every node and the subsample degenerates.
3. **Turn-only subsampling** (>30°): completed in 672 s but **62/139** —
   63 of 98 topology-solved nets emitted zero copper. The corridors
   serialize every net through the same skeleton channels; later nets'
   segments fail against Stage 4's shared occupancy grid, where free A*
   would route around. Corridor waypoints *constrain* Stage 4 and degrade
   connectivity by ~27 nets on this board.
4. **Pad-waypoint emission** (shipped): the emitted `uses_channels` is one
   id per consecutive pad pair (topology-decided order — given order for
   2-pad nets, sorted for multi-pad, matching Stage 4's fallback
   convention exactly), encoding the pads' own coordinates. The full
   capacity-aware path is still computed, capacity-committed, and
   post-condition-verified; only the *emission* is pad-based. Result:
   **89/139 = batched parity, 318 s**. (The intermediate skeleton-edge
   endpoint emission measured 86/139 — the pad-adjacent skeleton nodes
   force pad breakout through congested nodes where free A* routes
   around.)

**The honest conclusion**: Stage 4's occupancy-grid A* is a complete router
from raw pad positions (`docs/evidence/2026-08-08-terminal-defect-and-pad-
connectivity-fix.md`'s independent finding that topology was never consumed
under net-batching was not an accident — Stage 4 does not need corridors on
this board, and forcing them through it costs ~27 connected nets). The
vacuity fix's deliverable is that Stage 3 *decides* a real, capacity-aware,
connected topology (the connectivity-forcing constraint the SAT model
lacked) — not that Stage 4 be forced to follow its every edge. The emitted
pad pairs carry the topology's *decision* (which pads connect, in what
order, capacity-feasible) without constraining the geometric search.

## Tests

- `temper-rust-router-core/src/direct_topology.rs` unit tests: the vacuity
  regression (a two-pad net MUST receive non-empty `uses_channels`),
  capacity enforcement (over-capacity bridge re-routes the second net),
  spur out-and-back double-traversal, spur over-capacity → unrouted,
  multi-pad chaining, disconnected-pads → degraded, Stage-4-parseable
  channel ids, determinism, single-pad skip, unlimited no-capacity edges.
  Registered in the wasm test registry (3447 → 3452 tests).
- `packages/temper-placer/tests/router_v6/test_stage3_direct_solver.py`:
  pipeline-level vacuity regression, capacity-conflict re-route, degraded
  reporting, `_run_stage3` dispatch (direct is the default; the SAT escape
  hatch and net-batching priority preserved), post-condition raise.
- `test_adapter.py` pruning-wiring tests updated for the new dispatch:
  the default path builds no `ModelBuilder` at all; the SAT path (via the
  env hatch) still receives `enable_geographic_pruning` — the wiring-defect
  check they guarded is preserved where a `ModelBuilder` still exists.

## What this does NOT claim

- It does not change net-batching (the reference recipe) — that path is
  byte-unchanged and remains the measured baseline for comparison.
- It does not touch placement, Stage 4's A*, or the `clearance` DRC
  regression (attributed elsewhere to placement-density-driven F.Cu
  fragmentation).
- The direct solver is greedy: it never *proves* infeasibility. Unrouted
  nets are reported per-net, never silently dropped — Stage 4's existing
  fallback path is the documented degraded outcome, same as the batched
  path's `degraded_nets`.
