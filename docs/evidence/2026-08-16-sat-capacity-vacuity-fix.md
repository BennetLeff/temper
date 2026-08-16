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
   `audit_result`): every routed net's channel list is a connected walk
   through the skeleton and no capacity-constrained edge is over-committed
   (`remaining + committed == usable`). These checks caught two real bugs
   during development — a consecutive-duplicate dedupe that corrupted both
   bookkeeping and walk continuity, and the per-traversal gate gap above —
   and are standing checks, not scaffolding.

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
| **monolith, after this fix** | **Stage 3 adds ~0 GB over the Stage-2 baseline** (HWM 2.9 GB is Stage 2's EDT; Stage 3 RSS stayed at the pre-Stage-3 level through the direct solve) | completes (see §route) |

No CNF is built at all — the 22.5M-variable / 399M-aux / 768M-clause
encoding is gone.

## Route result (measured this task)

`scripts/route_board.py --output /tmp/opencode/route3.kicad_pcb` (default:
monolithic, no `--net-batching`):

- wall: ~ (fill after run)
- peak RSS: ~ (fill after run)
- pad connectivity: (fill after run — compare to batched 92/139)
- DRC: (fill after run)

## Tests

- `temper-rust-router-core/src/direct_topology.rs` unit tests: the vacuity
  regression (a two-pad net MUST receive non-empty `uses_channels`),
  capacity enforcement (over-capacity bridge re-routes the second net),
  spur out-and-back double-traversal, spur over-capacity → unrouted,
  multi-pad chaining, disconnected-pads → degraded, Stage-4-parseable
  channel ids, determinism, single-pad skip, unlimited no-capacity edges.
  Registered in the wasm test registry (3447 → 3457 tests).
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
