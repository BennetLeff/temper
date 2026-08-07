# Wave 4 triage: `router_v6/constraint_model.py` — JUSTIFIED-KEEP, no port

<!-- provenance: commit=4884d284cde3b8247ae90727d8374d3aac98c5b8 dirty=false -->

Target crate assigned: `packages/temper-io-types`. Source: `packages/temper-placer/src/temper_placer/router_v6/constraint_model.py`
(653 LOC at origin/main `4884d284c`).

**Verdict: no port.** This file is a dataclass/Protocol type hierarchy plus SAT-model
build orchestration. It contains no separable numeric or geometric kernel that would
benefit from a Rust FFI boundary, and the little arithmetic it does contain is entangled
with unmigrated Python types (`networkx`-backed `ChannelSkeleton`, `DesignRules`,
`ParsedPCB`) that would have to move first for a port here to make sense. This matches
the program's own prior read: the 2026-08-04 dispatch-readiness handoff
(`docs/handoffs/2026-08-04-wave4-phase45-dispatch-readiness.md`, row 3) already lists
`constraint_model` as a **Keep**, grouped with `routing_results.py` under the R7
"Phase 2 contracts" JUSTIFIED-KEEP class recorded in PR #622 (blocker: "9 unmigrated
router_v6 types"). This document gives `constraint_model.py` its own named blocker
rather than relying on the group mention.

## What the file actually is

- Lines 27–202: five `@dataclass(kw_only=True)` types (`Variable`, `NetChannelVar`,
  `NetLayerVar`, `ViaVar`, `OrderVar`) and four `Constraint` subclasses
  (`CapacityConstraint`, `DiffPairConstraint`, `LayerConstraint`,
  `ChannelSeparationConstraint`) — field declarations plus, for three of the four
  constraints, an `esl()` method returning a closure used later by the BMC
  (bounded-model-checking) verifier in `esl.py`. No loops over geometry, no
  linear algebra.
- Lines 205–243: `ConstraintModel`, a plain container (`list`/`dict` bookkeeping,
  `len()` properties).
- Lines 245–556: `ModelBuilder`, which walks `ChannelSkeleton.graph.edges`/`.nodes`
  (a `networkx` graph — see `packages/temper-placer/src/temper_placer/router_v6/channel_skeleton.py:28,38,43,48`)
  and `ParsedPCB.components`/`pins`, producing string-keyed SAT variable/constraint
  objects (`f"uses_N{net_idx}_{edge_id}"` etc.). This is symbolic ID generation and
  dict/set bookkeeping over Python object graphs, not numeric compute.
- Lines 558–621: `ConstraintGenerationStage` (a pipeline `Stage`) and a
  `@register_validator` function — orchestration glue.

## Candidate kernels considered and rejected

1. **`CapacityConstraint.esl()`** (line ~162): `min_width = min(...)`;
   `max_nets = int(self.capacity * self.slack_factor / min_width)`. Three scalar ops.
   The surrounding docstring (added 2026-08-02, re-homed from
   `docs/solutions/logic-errors/unsound-atmostk-capacity-encoding.md`) documents a
   formally verified Sinz (2005) sequential-counter CNF encoding with an existing
   exhaustive-verification suite (3,286 SAT checks via an in-repo mini DPLL solver,
   cross-validated against pysat Glucose3 in `tests/router_v6/`). This is a
   closure returned for the Python-side BMC verifier to call during test-time
   assignment checking, not a hot-path routing kernel — re-implementing it in Rust
   would duplicate formally-verified logic for no runtime benefit and risk drifting
   from the proof.
2. **`_create_capacity_constraints`** net-width arithmetic (line ~436):
   `net_width = rule.trace_width_mm + rule.clearance_mm`. One scalar add, run inside a
   loop that exists to build a `dict`-keyed variable lookup — not a kernel in its own
   right.
3. **`_create_layer_constraints`** pin-position tolerance match (line ~529):
   `abs(node[0] - pin_pos[0]) < 0.01 and abs(node[1] - pin_pos[1]) < 0.01`. A single
   tolerance comparison per graph node, gated on `pin_world_position()` — a function
   defined in `core/pin_geometry.py`, outside this file, that itself depends on the
   `packages/temper-geometry` transform kernels a sibling agent owns today. Extracting
   this one comparison would still leave the caller iterating a `networkx` graph on the
   Python side; there is no standalone function boundary to FFI across.
4. **`_create_layer_constraints`**, line 503: `float(comp.initial_rotation or 0) *
   math.pi / 2.0` is computed and never assigned to anything — a dead expression
   (leftover from an earlier version of the function). Confirmed via read; not
   consequential enough to warrant its own PR, noted here for the record.

None of these rise to "genuine numeric/geometric kernel." All of them are single
scalar expressions embedded in control flow over unmigrated Python container types.

## Dead-code check

Grepped every top-level class/function in the file for callers across the repo
(excluding `.claude/worktrees/*` scratch copies):

- `ModelBuilder` — live. Constructed in
  `packages/temper-placer/src/temper_placer/router_v6/_pipeline_route.py:248,260`
  and by 8 test files under `packages/temper-placer/tests/router_v6/`.
- `ConstraintGenerationStage` — live. Registered/run as part of the router_v6 stage
  pipeline (referenced from `router_v6/__init__.py`, `_pipeline_types.py`).
- `ChannelSeparationConstraint` — live. Constructed by
  `packages/temper-placer/src/temper_placer/pcl/sat_bridge.py:213,378` (PCL
  `SeparatedConstraint` → SAT grounding). Note it has no `esl()` method, unlike its
  three sibling `Constraint` subclasses — that's a pre-existing gap in this file, not
  something introduced or masked by this triage.
- `validate_constraint_generation` — live, registered via `@register_validator`,
  invoked by the stage-validator harness (`stage_validators.py`).

No dead code found in this file. Everything is reachable; the "no port" verdict is
about kernel absence, not disuse.

## Why this stays Python for now

The blocker is the same shape as the one already recorded for `routing_results.py`:
`ModelBuilder` reads and writes types that have not themselves migrated —
`ChannelSkeleton` (networkx-backed, itself flagged as "shapely Voronoi spike-gated" in
the same dispatch-readiness table), `DesignRules`, `ParsedPCB`, `Net`, `DiffPair`, and
the PCL `CompilationContext`/`CompilationTarget` bridge. A Rust port of the
variable/constraint *builder* without first porting the graph and PCB types it walks
would mean either (a) marshalling a `networkx.Graph` and several dataclass trees across
the FFI boundary on every call for no compute win, or (b) forking the builder logic
into two implementations that must stay behaviorally identical — both worse than
leaving it in Python until the upstream types land.

## Process notes

- No Rust code was written; `packages/temper-io-types` is untouched by this branch.
- Per the task's disk-safety instruction, `df -g /Users/bennet` was checked before
  starting (28 GB free, well above the 8 GB floor) and no build was run since no
  Rust changed.
- No PBT/differential/oracle scaffolding was added, since there is no kernel to pin.
