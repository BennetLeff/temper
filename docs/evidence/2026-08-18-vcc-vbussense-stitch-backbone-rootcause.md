<!-- provenance: commit=11a7e7c52d21ebca3ff8ff06e6e3b941441189fd dirty=false (worktree agent-a9684758c5ea3beaf, main tip at task start). pcb/temper.kicad_pcb sha256 26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b at stub time, matches task brief -- this stub is a placeholder written before any board write, per this project's survival rule (a worktree with no commits is destroyed when the agent stops). -->
---
title: "vcc and V_BUS_SENSE have zero stitch segments at any width -- root cause (placement-infeasibility finding, no code fix exists)"
date: 2026-08-18
module: temper-placer
tags: [router, zone-stitch, power-islands, c-space, drc, connectivity]
problem_type: drc-defect
status: done
---

# vcc / V_BUS_SENSE: zero-stitch-segment root cause (placement-infeasibility finding)

**Status: DONE.** Root cause measured and attributed; no legitimate
emission-code fix exists under this task's HARD RULES (see Conclusion
below); `pcb/temper.kicad_pcb` left untouched.

## Task, per the coordinating brief

Of the four `POWER_ISLAND_NETS`, `+3V3` (89 segments) and `+15V` (32
segments) kept genuine 1.0mm backbone copper after PR #1332's collision
check landed. `vcc` (0 segments, 11 vias) and `V_BUS_SENSE` (0 segments, 3
vias) kept none -- every MST backbone edge for both rails collided at the
corrected 1.0mm width and was dropped fail-closed, per
`docs/evidence/2026-08-17-board-write-stitch-width-and-collision-fix.md`
(`vcc`: 12 edges + 2 stubs dropped; `V_BUS_SENSE`: 3 edges + 1 stub
dropped -- 100% of both rails' edge sets).

Root-cause why every edge collides for these two rails specifically
(routing order / MST topology / corridor width / via-drop placement), fix
it in `_power_islands.py` (checking `_ground_plane.py` for a twin) if
tractable at 1.0mm, or document the placement-infeasibility finding with
evidence if not. Hard constraints: stitch width floor 1.0mm (never lower),
PR #1332's collision check stays (never weaken/bypass), no
clearance/creepage/DRU/copper-weight threshold changes, no
`pcb/temper.kicad_pcb` write without reporting first.

Board identity at task start: main `11a7e7c52d`, board sha256
`26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b`
(unchanged; not touched by this task except with explicit reporting
first).

## Plan

1. Read `_power_islands.py` end to end: MST construction, primary A*
   corridor-backbone pass, `_blocked()` fallback, via-drop stub emission.
   Diff against `_ground_plane.py` for the clone-drift pattern already
   found 3x this project.
2. Instrument/measure why `vcc` and `V_BUS_SENSE` specifically hit 100%
   collision -- net ordering (are they routed after `+3V3`/`+15V` consume
   the shared corridors?), MST edge geometry (edge length/routing through
   congested areas), corridor width at 1.0mm+clearance, via-drop offset
   geometry.
3. Fix the largest tractable cause in `_power_islands.py` (and
   `_ground_plane.py` if a twin function is implicated), or write up the
   placement-infeasibility finding with geometric evidence.
4. Re-route from a scratch copy (isolated venv, verify
   `temper_placer.__file__` resolves inside this worktree), determinism
   check (two byte-identical routes), full DRC re-measurement against the
   task's ledger (shorting_items <=42, clearance <=189, HV<->LV creepage
   <=77, connectivity >=60/139, fake completions <=6 by name,
   track_width stays 0).
5. Report the full ledger, fake completions by name, any `_ground_plane.py`
   twin touched.

(To be continued in this same file, appended incrementally as measurements
land.)

## Reframing (coordinator-relayed sibling finding, corroborated independently below)

Mid-task the coordinator relayed a sibling's finding from the OTHER 6-fake-
completions investigation: the pour-plane generators' corridor-A* MST
backbone lands only ~0-1 of ~9-87 attempted edges per rail on this board,
board-wide -- i.e. `vcc`/`V_BUS_SENSE` having zero backbone is not a
special case; it is the SAME near-universal edge-routing failure that
leaves `+3V3`/`+15V`/`gnd` critically short too, just realized worse for
the two smallest rails. This section's own measurements (gathered before
and after that message, using this task's own instrumentation) confirm it
independently, with attribution.

## Instrumentation added (kept permanently, logging-only)

`_power_islands.py` and its twin `_ground_plane.py` both computed
`mst_edges_astar_routed_count` / `mst_edges_fallback_count` /
`mst_edges_dropped_count` per net (`PowerIslandResult`/`GroundPlaneResult`
fields) but never logged them anywhere production reads -- the caller
(`_adapter_convert.route_pcb`) discards the per-net results dict entirely.
Commit `cf4026bac` adds, to BOTH files (this is exactly the clone-drift
pattern already documented between them -- fixed on both sides):

- An always-on per-rail "backbone summary" (`logger.warning`, visible by
  default): pads, MST edges attempted, landed via corridor-aware A*,
  landed via the keepout-only fallback, dropped entirely.
- `_power_islands.py` only: reason attribution on `_blocked()`'s
  rejections (keepout vs. pre-existing other-net copper vs. this-run's
  routed-signal/gnd copper vs. an earlier-processed rail's own new
  copper), and a corridor-mask reachability diagnostic that replicates
  `corridor_aware_spanning_edges`'s own growing nearest-label search (so
  it doesn't undercount reachability the way a raw exact-cell lookup
  would -- confirmed this mattered: an earlier, uncorrected version of
  this diagnostic wrongly reported `vcc` as 100% unreachable; the
  corrected version below shows the real picture is more specific and
  more interesting than that).

No routing/collision-check/threshold behavior changed -- verified by
reproducing the exact same segment/via counts, connectivity, and
fake-completion list across two full production routes run before and
after adding this instrumentation (see Measurement below).

## Measurement: real production route, isolated venv, instrumented

Environment: `make venv-isolate` in this worktree (`unset CONDA_PREFIX`
first, required). Verified directly: `temper_placer.__file__` resolves to
this worktree's own `packages/temper-placer/src/...` (not the shared
checkout), `temper_placer.router_v6._power_islands.STITCH_TRACE_WIDTH_MM
== 1.0`. `kicad-cli --version` = 10.0.5.

`scripts/route_board.py` default flags (strips existing copper first --
segments/vias/zones -- so the router faces a bare, placement-only board,
matching every prior evidence doc's methodology and NOT the same as
re-running the generator directly against the already-routed committed
board, which artificially inflates the HV keepout via routed HV traces --
an early attempt at this diagnostic made exactly that mistake and is
disclosed, not hidden, in this document's own git history), from a scratch
copy of `pcb/temper.kicad_pcb` (sha256
`26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b`,
verified unchanged throughout -- this task never wrote the committed
board).

Two full routes: route1 (v1 diagnostic, pre-correction) and route1 (v2,
corrected reachability diagnostic, same routing code). Both wall ~440-580s.

### Per-rail attempted-vs-landed (the four `PowerIslandResult`/
### `GroundPlaneResult` counts the coordinator asked for, read directly)

| net | pads | MST edges attempted | landed via corridor-A* | landed via keepout-only fallback | DROPPED |
|---|---|---|---|---|---|
| `gnd` | 88 | 87 | 7 | 2 | 74 |
| `+3V3` | 50 | 49 | 4 | 0 | 43 |
| `vcc` | 13 | 12 | 0 | 0 | 12 |
| `+15V` | 10 | 9 | 0 | 0 | 9 |
| `V_BUS_SENSE` | 4 | 3 | 0 | 0 | 3 |

**This is the coordinator's own diagnostic Case 1, unambiguously**:
`dropped` high, `astar_routed` ~0 (0 for 3 of 5 nets, 8-9% for the other
two) across every single one of the 5 pour-plane nets, not just
`vcc`/`V_BUS_SENSE`. Edges fall through to the straight-line `_blocked()`
probe and PR #1332's collision check correctly, fail-closed, rejects
essentially all of them (`0` rerouted via one-bend detour for
`+3V3`/`vcc`/`+15V`/`V_BUS_SENSE` in this exact run; `2` for `gnd`). **The
defect is corridor-A* reachability, not the collision check** -- exactly
the coordinator's own predicted Case 1.

### Why: keepout-dominated, NOT routing-order (measured, not inferred)

`_blocked()` fallback rejection attribution (own script, first-match-wins
per test, own new instrumentation), this run:

| net | keepout | pre-existing other-net copper | this-run's routed-signal/gnd copper | earlier-rail-this-run |
|---|---|---|---|---|
| `+3V3` | 1964 | 131 | 12 | **0** |
| `vcc` | 132 | 12 | 0 | **0** |
| `+15V` | 72 | 9 | 0 | **0** |
| `V_BUS_SENSE` | 9 | 0 | 0 | **0** |

**"Routing order" (the brief's first candidate) is definitively ruled
out**: `earlier_rail_this_run` -- an earlier-processed rail's OWN new F.Cu
copper this run, the only order-dependent obstacle in the whole
pipeline -- is exactly **zero** for every rail measured, including `vcc`
(processed 2nd, right after `+3V3`, the rail with the most new copper).
Reprocessing `vcc`/`V_BUS_SENSE` first would not recover a single edge;
the obstacle that rejects them isn't there yet either way. `keepout`
dominates by 1-2 orders of magnitude over every other reason combined, on
every rail.

`keepout` = the union of a **14.1mm-radius disc around every individual
HV-domain pad** (`compute_hv_selv_keepout`: `DEFAULT_CORRIDOR_WIDTH_MM`
(`MIN_BARRIER_WIDTH_MM` 12.6mm PD3 reinforced creepage + 0.5mm cushion) +
`KEEPOUT_EXTRA_MARGIN_MM` 1.0mm) -- a safety-derived SSOT value this
task's HARD RULES forbid touching, and (per `_collect_hv_copper_geometry`'s
own docstring) already the LEAST aggressive of three approaches tried --
HV tracks and existing HV zone outlines were both tried and reverted for
measured over-collapse of routability; per-pad-centre buffering (not a
global band, which was tried first and found geometrically wrong for this
board's interleaved HV/SELV pads) is what remains.

### Why `vcc`/`V_BUS_SENSE` specifically get ZERO where `+3V3`/`gnd` get a
### little: fragmentation + pad count, not a different mechanism

Corridor-mask reachability (own instrumentation, replicating
`corridor_aware_spanning_edges`'s own 15-cell/3.0mm growing nearest-label
search so it isn't an undercount):

| net | own positions | totally unreachable (no labelled cell within 3mm) | reachable positions split across N DISTINCT components |
|---|---|---|---|
| `+3V3` | 50 | 13 | **17** components (37 reachable positions) |
| `vcc` | 13 | 2 | **10** components (11 reachable positions) |
| `+15V` | 10 | 1 | 9 components (9 reachable positions) |
| `V_BUS_SENSE` | 4 | 0 | **4** components (4 reachable positions -- every single one alone) |

`corridor_aware_spanning_edges` only ever attempts a real A* path between
TWO POSITIONS OF THE SAME RAIL THAT ALREADY SHARE A CORRIDOR-MASK
COMPONENT (a hard topological fact under 1.0mm erosion, not a search
budget -- `route_edge_astar`'s own window schedule already escalates to
the UNCONSTRAINED FULL GRID as its last resort, so a component boundary
here means no path exists at ANY window size, not merely that a small
window missed one). `V_BUS_SENSE`'s 4 reachable pads land in 4 DIFFERENT
components -- by construction, zero same-component pairs exist, so zero
edges are ever even attempted via A*. `vcc`'s 11 reachable pads land in 10
different components -- essentially the same story, one coincidental pair
sharing a (16mm^2) component that still didn't resolve. Free space DOES
exist near most of these pads individually (`vcc`'s largest reachable
pocket alone is 47263 cells =~ 1890mm^2), but it is fragmented by the
14.1mm keepout into many MUTUALLY DISCONNECTED islands, and these two
rails simply do not have enough pads for two of them to land in the SAME
island by chance. `+3V3` (50 pads) and `gnd` (88 pads) get a little real
backbone (4 and 7 A*-solved edges respectively) for the same reason a
larger sample is more likely to contain a coincidental pair -- not because
their geometry or code path differs from `vcc`/`V_BUS_SENSE`'s. **This is
one mechanism at one severity gradient, not two different defects.**

### Ruling out the other three named candidates

- **MST topology**: not independently fixable. `corridor_aware_spanning_edges`
  already computes its OWN local MST within each corridor-mask component
  (not the global Euclidean MST's possibly-infeasible edge list), so
  every same-component pair is already optimally connected. A different
  global spanning structure cannot manufacture a path between two
  positions in provably disconnected components -- disconnection here is
  a property of the eroded grid's connected-components labelling, checked
  against the FULL board with an unconstrained window, not a topology
  choice.
- **Via-drop placement**: a real, but secondary, cost -- `vcc` placed
  11/13 vias cleanly (2 unresolved), `V_BUS_SENSE` 3/4 (1 unresolved);
  small compared to the 12/3 MST edges dropped. Widening the via-search
  ring would not help the BACKBONE specifically: `mst_edges`/
  `corridor_aware_spanning_edges` operate on the PAD's own position, not
  the via's (possibly offset) landing point -- moving a via further away
  changes nothing about whether two PAD positions share a corridor-mask
  component.
- **Corridor width**: this IS the mechanism, confirmed above -- not a
  bug, the DIRECT, measured, dominant, and (per HARD RULES) untouchable
  cause.

## Conclusion: placement/pour-topology finding, not an emission-code defect

**Corridor-A* (and its keepout-only fallback) genuinely cannot route real
backbone connectivity for `vcc` and `V_BUS_SENSE` at 1.0mm width given the
current placement.** Not a routing-order defect (measured: zero
contribution), not a search-budget limitation (the full grid is already
tried), not a collision-check defect (PR #1332's check is behaving
exactly as designed -- fail-closed on a genuinely infeasible edge). The
safety-mandated 14.1mm HV/SELV keepout radius (immutable under this
task's HARD RULES) fragments the board's free F.Cu space into many small,
mutually disconnected islands; `vcc` (13 pads) and `V_BUS_SENSE` (4 pads)
are too sparse for two of their own pads to coincidentally land in the
same island. `+3V3` and `gnd` are not succeeding where these two fail --
they are failing 88% and 85% of the time respectively, just with enough
raw pad count that a few coincidental pairs still land a little real
copper. **No fix inside `_power_islands.py`/`_ground_plane.py`'s emission
logic can create backbone connectivity between two corridor-mask
components that do not share a path at any window size, without either
narrowing the keepout (forbidden), narrowing the trace width (forbidden),
or weakening the collision check (forbidden).** This converts the task
into placement/pour-topology work: `vcc`/`V_BUS_SENSE` (and, less
severely, `+3V3`/`+15V`/`gnd`) would need either a placement pass that
clusters each rail's own pads so more of them land in one shared
keepout-free island, or a genuinely different pour-topology strategy for
sparse rails (e.g. accepting via-only connectivity plus a real KiCad zone
fill, which `pad_connectivity_audit` does not currently credit -- flagged
for the sibling coordinating the residual-fake-completions investigation,
since the two threads share a root cause but the fix, if any, is a
placement/metric question, not this module's).

No board write: there is no legitimate emission-path fix to apply given
the HARD RULES, so `pcb/temper.kicad_pcb` is left untouched, per the
task's own accepted "documented finding" outcome.

## Full ledger vs. the task's success criteria

Own `kicad-cli 10.0.5` DRC run (`--severity-all --all-track-errors`,
proper env: `fp-lib-table` + `pcb/libs/` copied alongside the scratch
board + `_single_threaded_kicad_env` -- confirmed correct by
`lib_footprint_issues`=13/`lib_footprint_mismatch`=26 reading as their
TRUE split rather than the 168/0 pair the coordinator flagged as the
omitted-env failure signature), no-refill mode, on route1(v2)'s output
(segments=4553, vias=169, zones=151 -- byte-for-byte-equivalent per-net
segment/via counts to both route1(v1) and the currently committed board):

| criterion | target | measured | verdict |
|---|---|---|---|
| `track_width` | stays 0 | **0** | MET |
| `shorting_items` | no worse than 42 | **39** | MET |
| `clearance` | no worse than 189 | **179** | MET |
| HV<->LV creepage | no worse than 77 | **77** | MET (exactly at the floor) |
| connectivity | >= 60/139 | **60/139** | MET |
| fake completions | <= 6, named | **6**: `+15V, +3V3, GATE_LS, V_BUS_SENSE, gnd, vcc` | MET |
| two byte-identical routes | determinism | two full routes (v1/v2, differing only in this task's own logging instrumentation) produced IDENTICAL segments=4553/vias=169/zones=151, IDENTICAL per-net segment/via counts, IDENTICAL 60/139 connectivity, IDENTICAL 6-net fake-completion list -- a `pcb.kicad_pcb`-level sha256 was NOT byte-identical (tstamp/UUID churn only, the same cosmetic noise band prior evidence docs document) since no board write/commit-worthy routing change exists to re-verify at that granularity | Routing-content-identical across both diagnostic runs; genuine byte-identical sha256 not separately re-verified this session since this task makes no routing-behavior change to verify |

**Fake completions, named, cross-checked 3 ways** (router's own log,
independent per-net segment/via count from the output board, and this
document's own creepage/shorting breakdown): `+15V, +3V3, GATE_LS,
V_BUS_SENSE, gnd, vcc` -- 6, matching the ceiling exactly. `vcc` and
`V_BUS_SENSE` are 2 of these 6; the other 4 are `+15V`/`+3V3`/`gnd` (same
mechanism, this document) and `GATE_LS` (a different mechanism, not
investigated here -- out of this task's stated scope).

## `_ground_plane.py` twin: touched

Per the coordination note ("if you fix a function with a twin, fix or
report both"): `_ground_plane.py` had the IDENTICAL missing-visibility gap
(computed `mst_edges_astar_routed_count`/`mst_edges_fallback_count` but
never logged them) -- fixed alongside `_power_islands.py` in the same
commit (`cf4026bac`), same log message shape, so a future reader gets the
same attempted-vs-landed visibility for `gnd` that this task added for
the four `Power`-class rails. No other divergence found this session: the
two files' `_blocked()` implementations were compared line-by-line and
remain structurally aligned (same 3-obstacle-category check order, same
buffered-footprint discipline) -- the only prior divergence (the
zero-width-probe / missing-obstacle-check bug) was already closed by PR
#1332 on both sides.
