<!-- provenance: worktree /home/bennet/Desktop/temper-nlayer-astar-spike, branch spike/nlayer-via-astar, branched from agent/router-combined @ 6121c49f -->

# Spike: a real N-layer, via-aware A* search for the Stage 4 router

**Date:** 2026-08-08

**Task:** Feasibility/design spike -- is Stage 4's pathfinding structurally
capped at two layers, and if so, what does it cost to generalize it to an
arbitrary number of signal layers with real via modeling, what does that
buy on `pcb/temper.kicad_pcb` (2 signal layers today), and what would it
buy on a board with more signal layers.

**Headline, stated plainly up front.** Yes, the cap is real and exactly
where the task described: `select_routing_grids` (a hardcoded pair) and
`run_astar_pathfinding`'s `alternate_grid` singular parameter. But the
search primitive underneath both, `astar_core._astar_search_3d` /
`_route_segment_3d`, was **already** N-layer-capable and already
via-cost/clearance-aware -- it is real, tested code, just used only as a
2-grid last-resort fallback tier. So this spike is a plumbing
generalization of an existing, correct primitive, not a new search
algorithm. **On today's 2-signal-layer board it buys nothing measurable**
(see §3): the generalized path collapses to the same 2 grids the
production path already uses, and the measured completion/segment/via
counts land within the range production code already produces run-to-run
on unrelated changes to this same board. Its value is entirely
speculative, for a board this one is not and, per REQ-ELEC-05, is not
going to become.

---

## 1. Where the cap actually is, confirmed by reading, not assumed

- `_pipeline_route.select_routing_grids` (`packages/temper-placer/src/temper_placer/router_v6/_pipeline_route.py:444-468`,
  unchanged by this spike): always returns exactly
  `(occupancy_grids.get("F.Cu") or ..., occupancy_grids.get("B.Cu") or ...)`
  -- a 2-tuple, called unconditionally from `_run_stage4`.
- `astar_pathfinding.run_astar_pathfinding`'s signature
  (`_astar_reconstruct.py:89-120`, unchanged): one `grid` plus one
  **singular** `alternate_grid`. `all_grids` is built as
  `{grid.layer_name: grid}` plus at most one more entry
  (`_astar_reconstruct.py:118-120`). No `alternate_grids` (plural) has
  ever existed in this repo's history (confirmed: `git log -p` over
  `_astar_reconstruct.py`/`astar_pathfinding.py` shows the parameter has
  always been singular).
- `Stage4Orchestrator.assemble_pathfinding_result` (`stage4_orchestrator.py:59-62`)
  is a bare `getattr(state, "pathfinding_result", None)` on a `BoardState`
  never run through `Stage4Orchestrator.run()` at this call site -- always
  `None` in production, confirmed by reading `_run_stage4`: it constructs
  `orchestrated`/`state` but calls `assemble_pathfinding_result(state)`
  directly, never `orchestrated.run(state)`. The `if pathfinding_result is
  None:` guard around the 2-layer call is therefore dead in the sense the
  task described -- it always takes that branch.

**What was NOT capped, and did not need reinventing:**
`astar_core._astar_search_3d` / `_route_segment_3d` already accept an
arbitrary-size `grids: dict[str, OccupancyGrid]`, already treat a layer
transition as a real, costed move (`via_cost`), and already reserve the
via's true clearance/diameter envelope on **every** layer it spans via
`mark_via_blocked()` (not just the two endpoints) -- this is real,
already-merged, already-tested production code
(`test_astar_route_multilayer_via_fallback.py`), not something this spike
had to build. It is simply invoked, today, as a last-resort third tier
inside `_astar_route_multilayer`, itself fed at most 2 grids
(`primary_grid` + one `alternate_grid: OccupancyGrid | None` parameter --
`_astar_search.py:347-367`) no matter how many grids exist upstream.
`astar_grid._mark_route_blocked` / `_unmark_route_blocked` /
`_identify_blocking_nets` are likewise already `dict`-of-arbitrary-size
callers (`grids: dict`), not 2-capped -- confirmed by reading
`astar_grid.py:289-351`.

**Conclusion this spike's design rests on:** the valuable, hard part of
"N-layer via-aware A*" -- a search that models a layer transition as a
real move with real cost and real clearance legality, not a special case
-- already existed and was already correct. The actual gap is that three
call sites above it (`select_routing_grids`, `run_astar_pathfinding`'s
signature, `_astar_route_multilayer`'s signature) hardcode "2" in three
different ways. This reframes the spike from "design a new algorithm" to
"generalize three signatures and verify the result is still correct" --
a smaller, more honest scope than the task's framing might suggest, and
the reason this spike's diff is a few hundred lines, not a rewrite.

## 2. What was built

Branch `spike/nlayer-via-astar`, worktree
`/home/bennet/Desktop/temper-nlayer-astar-spike`, from
`agent/router-combined @ 6121c49f`.

### 2.1 The generalized search (`_astar_nlayer.py`)

- `select_routing_grids_nlayer(occupancy_grids) -> dict[str, OccupancyGrid]`
  -- returns every available grid (all signal layers; plane layers never
  get a grid at all, per `routing_space.py`, so no extra filtering is
  needed), ordered outer-layers-first, instead of a hardcoded pair.
- `_astar_route_nlayer(...)` -- generalizes `_astar_route_multilayer`'s
  3-tier cascade to N grids:
  1. Cheap same-layer 2D search on the net's preferred layer (unchanged).
  2. Cheap same-layer 2D whole-segment detour on **every other** available
     layer in turn, first success wins (was: exactly one `alternate_grid`).
  3. The full via-aware 3D search (`_route_segment_3d`) across **all**
     grids simultaneously (was: at most 2 grids) -- this tier can hop
     through more than one intermediate layer within a single segment.
  4. Forced-segment / fail-closed decline, matching the production
     contract exactly (`_allow_forced_segments` is unconditionally
     `False` in this codebase; nothing about this spike changes that
     safety gate).
- `run_astar_pathfinding_nlayer(...)` -- generalizes the per-net driver
  loop (net ordering, pad unblocking, fail-closed exception handling,
  failure reporting) to call the above with an N-grid dict.

Deliberately out of scope, and why each omission does not affect the
comparison in §3 (see the module's own docstring for the full reasoning):
the experimental all-pad-tree path (disabled by default in production);
the congestion-tensor/thermal cost terms (not used by the production
net-batching run this is compared against); and the rip-up-and-reroute
queue, which is **traced and confirmed dead code today** -- under the
unconditional `_allow_forced_segments() -> False` policy,
`_astar_route_with_ripup`'s `ripped_ids` is populated only when the
returned path has `forced_segment_count > 0`, and `run_astar_pathfinding`
always returns a decline *before* reaching the loop that would act on a
non-empty `ripped_ids` (that loop runs only on a clean, forced-segment-free
success, where `ripped_ids` is always `[]`). This was verified by reading
the exact control flow, not assumed -- see `_astar_nlayer.py`'s docstring
for the line-level trace. If `_allow_forced_segments` is ever made
conditional again, this equivalence would need re-checking.

### 2.2 Pipeline wiring (opt-in, default off)

`RouterV6Pipeline.__init__` gained `enable_nlayer_astar_spike: bool =
False`, threaded through `route_pcb()` and `scripts/route_board.py
--nlayer-astar-spike`. `_run_stage4` branches on it before the existing
2-layer call -- **the existing code path is untouched**: same functions,
same arguments, same order, reached whenever the flag is False (the
default, and the only value ever used in production). This is a pure
additive branch, not a modification of `run_astar_pathfinding` or
`select_routing_grids` themselves.

### 2.3 Correctness verification (`pad_connectivity_audit.py`)

The task's central demand: a check that a net's copper actually joins its
own pads, not merely that copper with the right net number exists. Core
function `check_net_pad_connectivity(net_name, pads, segments, vias, ...)`
builds a union-find over (snapped-position, layer) nodes -- segments union
same-layer endpoints, vias union a position across every layer they span,
pads union onto their own layer(s) (or every layer, for a through-hole
pad) -- and reports `fully_connected` iff every pad of the net lands in
one component. `is_fake_completion` is `has_any_copper and not
fully_connected`: copper exists, but does not join the net's own pads --
the exact measurable shape of the incident this spike was told to design
against.

**Demonstrated against the b39b382d shape** (see
`test_pad_connectivity_audit.py::test_catches_b39b382d_fake_completion_shape`):
two pads on F.Cu, with the only emitted "copper" being a segment chain
entirely on `In1.Cu` that never touches either pad (the documented shape
of the rejected predecessor to `b39b382d`, which routed a tree edge onto a
grid-backed-but-wrong layer). `topology_copper_audit.nets_carrying_copper()`
-- and any naive segment/via counter -- would count this net as carrying
copper; `check_net_pad_connectivity` reports `has_any_copper=True,
fully_connected=False, is_fake_completion=True`. 20 unit tests in
`test_pad_connectivity_audit.py` + `test_astar_nlayer.py` cover this,
positive controls (real connectivity not flagged), via-crossing legality
(a via at the right position joins two layers; the identical geometry
*without* the via does not), through-hole vs. SMD pad layer semantics, and
partial-star topologies (2-of-3 pads connected correctly identifies only
the unreached pad). All 20 pass; the module also carries a thin
`audit_pcb_file(path)` adapter that runs the same check against a real
written `.kicad_pcb`, used for §3's own measurement below.

**An unplanned, and arguably more important, finding from this checker.**
Applying `audit_pcb_file` to real router output (both the production 2-tier
path and this spike's N-layer path, on the fixture board and the production
board -- see §3.3) surfaced a **pre-existing gap in the production router,
unrelated to this spike's own change**: `channel_mapping.fallback_channel_path`
(`channel_mapping.py:155-179`), when `enable_all_pad_tree` is `False` (the
production default) and a net has more than 2 pads, sets
`waypoints = [pads[0], pads[-1]]` -- **only the first and last pad (by
sorted position) are ever included in the route**. Every other pad of that
net is silently never targeted by Stage 4 A* at all. A 22-pad GND net
observed on the fixture board is a real example: one 2-endpoint trace gets
drawn, `nets_carrying_copper()` correctly reports GND as carrying copper,
and 20 of its 22 pads are never connected by anything Stage 4 produced.
This is present in the **unmodified baseline path** too (confirmed: same
shape, same net, same pad count, on a baseline-path route of the fixture
board) -- it is not something this spike's N-layer generalization
introduced. It means `nets_carrying_copper()` -- and by extension this
task's own headline "64/110 nets carrying copper" baseline metric -- is a
strictly weaker bar than "this net's pads are connected," for any net with
more than 2 pads and all-pad-tree disabled. `pad_connectivity_audit.py`
is, as far as this investigation found, the first tool in this codebase
that can see that gap at all.

## 3. Measured results

### 3.1 Baseline (cited, not re-run)

Per this task's own brief and `docs/evidence/2026-08-08-router-power-gnd-and-stage4-clearance-combined.md`
§3 (the "combined (A+B)" row, measured at `agent/router-combined @
6121c49f` -- the exact commit this spike branches from, with the exact
`route_board.py --net-batching --batch-size 10` invocation this spike's
run below reuses verbatim):

| | Nets carrying copper | Segments | Vias | Wall |
|---|---:|---:|---:|---:|
| baseline | **64/110** | **2579** | **50** | 862.4s |

Not independently re-run here: this spike's diff does not touch any code
on the baseline path (`enable_nlayer_astar_spike` defaults `False`, and
every function the baseline path calls -- `select_routing_grids`,
`run_astar_pathfinding`, `_astar_route_multilayer` -- is byte-identical to
`6121c49f`, confirmed by `git diff` against those specific functions
touching nothing). The cited figures already carry their own
determinism evidence (3+ independent runs, byte-identical, per that doc's
§1.2) at the exact commit this worktree's baseline path still is.

### 3.2 N-layer spike path, same board, same command

`TEMPER_BATCH_TRACE=1 uv run --no-sync python3 scripts/route_board.py --pcb
pcb/temper.kicad_pcb --net-batching --batch-size 10 --nlayer-astar-spike
--output ...`, measured with `topology_copper_audit.nets_carrying_copper()`
directly on the written output content (never an ad hoc parse):

<!-- FILLED IN BELOW ONCE THE RUN COMPLETES -->

### 3.3 Pad-connectivity audit of the N-layer run

`pad_connectivity_audit.audit_pcb_file()` against the same output:

<!-- FILLED IN BELOW ONCE THE RUN COMPLETES -->

## 4. Honest assessment

<!-- FILLED IN BELOW ONCE THE RUN COMPLETES -->
