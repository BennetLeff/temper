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
production path already uses -- the raw "nets carrying copper" count
does rise sharply (64/110 -> 96/110), but this spike's own
pad-connectivity check (§3.3, the correctness verification this task
required) proves that rise is entirely fake completion, the same shape
as the `b39b382d` incident this task warned against: the set of nets
whose pads are *actually* fully connected is the identical 31 nets on
both boards, verified by direct set comparison. Its value is entirely
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

### 2.4 A first measurement caught its own defect -- exactly the discipline this spike was told to apply

The first full production run of this spike's path reported
`nets_carrying_copper() = 96/110` -- dramatically higher than baseline's
64/110 -- with segments almost doubled (5016 vs 2579) and vias roughly
doubled (104 vs 50). Per this task's own warning ("this session has
watched routing metrics mislead three separate times"), this number was
**not reported** without first running `pad_connectivity_audit.audit_pcb_file()`
against that output. The audit immediately found the same shape as
b39b382d: dozens of "carrying copper" nets whose emitted geometry did not
reach their own pads (e.g. `GATE_HS`, a 2-pad net, showed a 104-segment
`B.Cu` chain with **zero vias**, starting 2.925mm from its own pad -- at
the exact position of R23's *other* pad, belonging to a different net).

**First hypothesis (partially right, not the real cause).** This spike's
driver had genuinely omitted a real production mechanism: production
`run_astar_pathfinding` derives a per-net iteration budget from waypoint
span (`_astar_reconstruct.py:189-201`, an elliptical estimate capped by
grid area) instead of using the flat `max_iter` for every net; this
spike's first version used the flat value everywhere. That is a real gap
(fixed -- see the committed diff, `run_astar_pathfinding_nlayer` now
derives the identical per-net budget), but re-measuring with the fix
**produced byte-identical output** (96/110, 5016 segments, 104 vias,
identical `GATE_HS` geometry) -- proof the budget was not, in fact, what
was driving this shape.

**Actual root cause, found by auditing a freshly run baseline with the
same tool.** Running `pad_connectivity_audit` against an independently
run **baseline** board (not the cited figures -- an actual fresh
`agent/router-combined @ 6121c49f` run, see §3.1) found
**the identical pathology in baseline's own output**: `GATE_HS` is
"routed successfully" in the unmodified production path too, with the
same wrong-pad geometry. This is conclusive: the wrong-endpoint shape is
a **pre-existing characteristic of the production pipeline**, present
before this spike existed, not something the N-layer generalization
introduced. Traced one level further: `channel_mapping.expand_channel_path_terminals`
returns a 2-pad net's SAT-derived waypoints **unchanged** (`channel_mapping.py:61-67`,
"Two-pad channel paths are intentionally returned unchanged") -- so
whatever waypoint Stage 3's topology/channel-skeleton extraction assigned
as a net's endpoint is trusted as-is, with no verification against the
net's actual pad position. For `GATE_HS`, that assigned waypoint
coincides with the position of R23's *other* pin (2.925mm away, on a
physically adjacent pad of the same 2-pin footprint) -- a Stage 3
topology-extraction defect, independent of layer count, that this spike's
correctness check surfaces but this spike does not fix (out of scope: it
predates and is orthogonal to the 2-vs-N-layer question this spike
exists to answer).

**Reconciling the two numbers precisely** (§3.3 has the full audit):
comparing the two boards' `pad_connectivity_audit` results net-by-net,
**the set of fully pad-connected nets is IDENTICAL between baseline and
the N-layer spike -- the same 31 nets out of 139 audited, verified by set
equality (`base_full == nlayer_full` is `True`), not just matching
counts.** The fake-completion count rises from 48 (baseline) to 82
(spike) -- a 34-net swing, matching almost exactly the 34-net rise in
Stage 4's own raw waypoint-completion count (52/104 -> 86/104, §3.2).
Every one of those additional nets is one with more than 2 physical pads
where only some subset actually got joined -- the same 2-of-N-pads-only
shape `fallback_channel_path` already produces today when
`enable_all_pad_tree=False` (documented in §2.3's "unplanned finding"),
just reached for more nets under the N-layer driver's search. **Zero of
those 34 nets moved from "not fully connected" to "fully connected."**
(The raw waypoint-completion rise from 52 to 86 -- a real, reproducible
difference in how many segment searches the two drivers complete given
identical waypoints on identical grids -- was not further root-caused
within this spike's time budget; see §4's productionizing estimate.)

Kept the budget fix in the committed code regardless (correct parity with
production regardless of whether it explains this particular gap), and
used the corrected, re-measured run as this doc's official numbers below.

## 3. Measured results

Both boards below are **freshly run in this task** (not only cited),
specifically so `pad_connectivity_audit` has real, comparable boards to
audit against each other (§3.3) -- the cited baseline evidence doc never
ran this check, because this check did not exist before this spike.
Both used the identical command
(`TEMPER_BATCH_TRACE=1 uv run --no-sync python3 scripts/route_board.py
--pcb pcb/temper.kicad_pcb --net-batching --batch-size 10 [--nlayer-astar-spike]`),
run concurrently on the same machine from the same worktree.

### 3.1 Baseline (freshly run, this task)

| | Nets carrying copper | Segments | Vias | Wall |
|---|---:|---:|---:|---:|
| baseline (fresh run) | **64/110** | **2579** | **50** | 712.4s |
| baseline (cited, `6121c49f`) | 64/110 | 2579 | 50 | 862.4s |

Byte-identical to the cited figures on every metric except wall time
(explained by this run sharing the machine with the concurrent spike run
below, not a behavior change -- confirms this worktree's baseline path is
still exactly `6121c49f`'s, and that this board/commit/command
combination is deterministic across three now-independent measurements:
the original doc's 3 runs, plus this one).

### 3.2 N-layer spike path, same board, same command

Measured with `topology_copper_audit.nets_carrying_copper()` directly on
the written output content (never an ad hoc parse):

| | Nets carrying copper | Segments | Vias | Wall | Raw waypoint-completion |
|---|---:|---:|---:|---:|---:|
| baseline | 64/110 | 2579 | 50 | 712.4s | 52/104 (50.0%) |
| N-layer spike | **96/110** | **5016** | **104** | 669.0s | **86/104 (82.7%)** |

("Raw waypoint-completion" = `route_board.py`'s own `Result: N/M nets
(P%)` line -- Stage 4's success count against whatever waypoints each net
was given, the same denominator/shape as the task's cited baseline
figure. Wall times are each run's own reported wall clock; both ran
concurrently on the same machine sharing CPU, so neither wall figure
should be read as a standalone performance claim -- see §4.)

Read in isolation, this table is the b39b382d shape almost exactly: a
completion figure that looks like a large win. It is not one -- §3.3.

### 3.3 Pad-connectivity audit: the real comparison

`pad_connectivity_audit.audit_pcb_file()` against both boards -- 139 nets
with at least one pad audited on each (every net with a footprint pin,
not just the 104-net Stage-4-attempted subset):

| | Nets audited | Fully pad-connected | Fake completion (b39b382d shape) | Honest gap (no copper, N/A) |
|---|---:|---:|---:|---:|
| baseline | 139 | **31** | 48 | 60 |
| N-layer spike | 139 | **31** | 82 | 26 |

**The fully-pad-connected set is not just equal in count, it is the
identical 31 nets** (`baseline_fully_connected_set == nlayer_fully_connected_set`
verified directly, not inferred from the counts). Every net the N-layer
path "gained" over baseline is a fake-completion net -- copper that
exists, carries the right net attribution, and would make
`nets_carrying_copper()` count it as done, but does not join all of that
net's physical pads. `GATE_HS` (§2.4) is one concrete example, present
identically in **both** boards' fake-completion lists.

**Known limitation of this specific audit run:** `pad_connectivity_audit`
does not model zone-pour connectivity (no polygon fill/flood-fill check --
see the module's docstring), so a zone-covered net (`SW_NODE`, `ac_l`,
etc. -- 32 zones on both boards) with no explicit segment/via lands in
the "honest gap" bucket even though a pour genuinely covers it. This
does not affect the headline comparison above: zone coverage is
identical on both boards (`zones=32` both runs, from the identical Stage
3/zone-regeneration code neither path touches), so it shifts baseline's
and the spike's "honest gap" counts by the same fixed amount and does not
touch the fully-connected-set-equality result, which is the finding that
matters.

## 4. Honest assessment

**What this buys on the current 2-signal-layer board: nothing measurable.**
The N-layer generalization is exercised on this board exactly as designed
-- `select_routing_grids_nlayer` returns `{"F.Cu", "B.Cu"}`, the same 2
grids production already uses, because that is genuinely every signal
layer this board has (`In1.Cu`/`In2.Cu` are GND/PWR planes, never given
an occupancy grid, per REQ-ELEC-05 -- confirmed, not assumed: `stage2.occupancy_grids`
only ever contained those two keys in every run this spike executed).
The measured result is exactly what that framing predicts: **zero
additional nets become genuinely pad-connected.** The 32-net rise in the
naive "carrying copper" count (§3.2, `nets_carrying_copper()`'s own
110-net denominator) is not evidence of anything working better -- the
independent pad-connectivity audit (§3.3, its own 139-net-with-pads
denominator, so the two counts are not directly additive) shows the same
effect as a 34-net rise in fake completion, matching the 34-net rise in
raw waypoint-completion almost exactly. Both measurements agree on the
same story from two different denominators: every one of these nets is a
partially-completed multi-pad net, a pre-existing codebase characteristic
(`enable_all_pad_tree=False` + `fallback_channel_path`'s first/last-pad
truncation) reached by more nets under this driver, not a new capability.
If this spike had reported the 96/110 headline without
running its own correctness check first, it would have reproduced
b39b382d's mistake almost exactly -- inflated completion, no real gain,
discoverable only by checking pad connectivity rather than trusting a
counter. That the check caught it, on this spike's own output, before
anything was reported, is the deliverable this task most cared about.

**What this would buy with more signal layers.** The generalization
itself is real and correctly demonstrated on synthetic fixtures (§2, the
N=3 test in `test_astar_nlayer.py`): given a board with 3+ genuine signal
layers, `_astar_route_nlayer`'s tier 3 (`_route_segment_3d` across every
grid) finds paths that a 2-grid-capped search structurally cannot express
at all -- proven by the paired positive/negative-control test (identical
fixture, 3 grids succeeds, the same fixture restricted to any 2 of the 3
fails closed). On a board where the inner layers are real routable signal
layers (not reference planes, unlike this one), this generalization would
plausibly unlock real completion gains via legitimate via crossings
through those layers, not fake ones -- but that claim is not measured
here, deliberately: doing so on synthetic fixtures only, per this task's
explicit constraint against repurposing this board's planes.

**What productionizing this would cost.** Roughly, in descending order of
effort:
1. **Root-cause the 34-net raw-waypoint-completion gap** (§2.4's closing
   note) -- found but not explained within this spike's time budget.
   Until explained, it should not be trusted as a real capability
   improvement even for the (here, vacuous) 2-endpoint completion metric.
2. **Root-cause the Stage-3 wrong-waypoint defect** this spike's own audit
   surfaced (`GATE_HS` and its like) -- present in production today,
   independent of this spike, but this spike is what found and
   demonstrated it with a concrete repro. Fixing it is likely higher-value
   than the N-layer generalization itself on this board, since it affects
   every 2-pad net's waypoint trustworthiness, not just multi-layer ones.
3. **Reintroduce the rip-up-and-reroute queue conditionally** -- currently
   dead code under `_allow_forced_segments() -> False`, but this spike's
   equivalence claim would need re-verification the moment that policy is
   ever revisited.
4. **Wire the all-pad-tree path** (`enable_all_pad_tree`) through
   `_astar_nlayer.py`, or -- likely higher leverage given finding #2's
   fallout -- fix `fallback_channel_path`'s first/last-pad-only behavior
   for >2-pad nets generally, since that is the single largest driver of
   the fake-completion/honest-gap split measured here (§2.3).
5. **Congestion tensor / thermal field threading** -- straightforward,
   not attempted here since the production comparison run uses neither.
6. Replace `select_routing_grids`/`run_astar_pathfinding`'s hardcoded
   2-grid signature with the N-grid one at the real call site
   (`_pipeline_route.py`), retire the parallel N-layer module, and re-run
   the full non-slow test suite (this spike ran its own 20 new tests plus
   the directly relevant existing 20 clean; the full ~2,500-test
   `router_v6` suite was started but not completed within this session's
   time budget -- see the commit log for what was and wasn't verified).

**What this risks.** Read naively, the raw "nets carrying copper" and
"raw waypoint-completion" numbers in §3.2 are a textbook case for
exactly the failure this task was designed to catch: they look like a
50%+ completion improvement and are not one. Any future work in this
area must carry the pad-connectivity check as a first-class gate, not an
afterthought -- this spike's own investigation needed two full production
routes and a targeted root-cause pass to avoid reporting a number nearly
identical in shape to the number this codebase already rejected once.

**Bottom line, stated as the task asked for plainly:** on
`pcb/temper.kicad_pcb` as it exists today, this generalization buys
nothing. The board has exactly 2 signal layers; the generalized search
collapses to the same 2 grids production already searches; and the one
genuinely N-layer-only capability (tier 3's simultaneous multi-grid via
search) is provably real only on synthetic fixtures with 3+ signal
layers, which this board structurally does not have and, per REQ-ELEC-05,
is not going to.
