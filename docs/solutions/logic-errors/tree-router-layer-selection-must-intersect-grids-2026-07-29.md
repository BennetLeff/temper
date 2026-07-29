---
title: "KeyError: 'F.Cu' -- the tree router picked a layer from the pads alone and never checked which layers it had an occupancy grid for"
date: "2026-07-29"
category: logic-errors
module: router_v6
problem_type: missing_validation
severity: critical
symptoms:
  - "Every all-pad-tree route on the production board crashed: router_v6/terminal_tree_execution.py:108 -- KeyError: 'F.Cu'"
  - "terminal_extraction.py correctly reported an SMD pad's declared layer as F.Cu, while occupancy_grid.py had built grids only for ['In1.Cu', 'In2.Cu'] -- F.Cu/B.Cu are outer copper-pour layers classified `plane`, and routing_space.py skips non-signal/mixed layers when building grids"
  - "a second, independent defect sat next to it: _pipeline_route.py's alternate-grid selection excluded the literal string \"F.Cu\" instead of the primary grid's actual resolved layer, so on a plane-outer board both the primary and alternate grid picks resolved to the same In1.Cu grid and In2.Cu never reached pathfinding at all"
root_cause: "_pick_route_layer computed a shared layer from the two terminals' declared layer_names alone, with no reference to which layers the router had actually been given an occupancy grid for, then unconditionally indexed grids[route_layer]. Any board where the pad's physical layer (F.Cu, outer) differs from the set of layers that get routing spaces (inner layers, because outer layers are classified `plane` when they carry copper pours) hits this: the layer that is geometrically correct for the pad is not a key in the dict the router is about to index."
resolution_type: code_fix
tags:
  - temper-placer
  - router-v6
  - keyerror
  - occupancy-grid
  - layer-selection
  - fabricated-completion
  - measurement-discipline
  - loc-ratchet
---

# `KeyError: 'F.Cu'` — the tree router picked a layer from the pads alone

## Context

Every all-pad-tree route attempted on the production board
(`pcb/temper.kicad_pcb`) crashed with `KeyError: 'F.Cu'` inside
`terminal_tree_execution.py:108`, `active_grid = grids[route_layer]`.
`route_layer` came from `_pick_route_layer`, which computed the shared
conductive layer between two tree terminals from their declared
`layer_names` alone, with no awareness of which layers the router had
actually built an occupancy grid for.

## Investigation Path

### Step 1: Trace the chain end to end, measured at each link

1. `pcb/temper.kicad_pcb` pours per-net copper on both outer layers,
   `F.Cu`/`B.Cu`. `io/_parse_board.py:264-272`'s zone heuristic reads that
   directly off the board and classifies both outer layers as `plane`
   (measured stackup: `[('F.Cu', 'plane'), ('In1.Cu', 'mixed'),
   ('In2.Cu', 'mixed'), ('B.Cu', 'plane')]`). This classification is
   deliberate, not a bug — see the "not fixed" section below.
2. `router_v6/routing_space.py:85` builds a routing space, and therefore
   an occupancy grid, only for `signal`/`mixed` layers. Measured:
   `occupancy_grids.keys() == ['In1.Cu', 'In2.Cu']`.
3. `router_v6/terminal_extraction.py:63` gives an SMD terminal its
   declared physical pad layer. Measured: `PAD LAYERS: ['F.Cu']` —
   correct, that is genuinely where the pad sits.
4. `terminal_tree_execution.py`'s old `_pick_route_layer` intersected the
   *pads'* declared layers with each other (not with the grid keys),
   returning `'F.Cu'`, then `grids['F.Cu']` raised `KeyError` because
   `grids` only ever held the layers from step 2.

### Step 2: A second, independent defect found while tracing

`_pipeline_route.py`'s `_run_stage4` selected the alternate occupancy
grid by excluding the *literal string* `"F.Cu"`, not the primary grid's
actual resolved layer:

```python
# before
fcu_grid = stage2.occupancy_grids.get("F.Cu") or next(
    iter(stage2.occupancy_grids.values()), None
)
bcu_grid = stage2.occupancy_grids.get("B.Cu") or next(
    (g for n, g in stage2.occupancy_grids.items() if n != "F.Cu"), None
)
```

On a plane-outer board, `occupancy_grids` never contains `"F.Cu"` or
`"B.Cu"` as keys at all — both lookups fall through to their `or` clause.
`fcu_grid` resolves to `next(iter(...))`, i.e. `In1.Cu` (dict iteration
order). `bcu_grid`'s exclusion (`n != "F.Cu"`) does nothing useful here,
since neither key is `"F.Cu"` — it also resolves to `In1.Cu`, the same
grid. **The router was handed one layer twice; `In2.Cu` never reached
pathfinding at all**, silently, with no error — this path never raises,
it just quietly halves the available routing space. Measured before the
fix: `primary grid layer: In1.Cu / alternate grid layer: In1.Cu`.

### Step 3: Two candidate fixes for the crash, both implemented and measured

* **(A) Reject the edge** — treat "no shared layer with a grid" the same
  way the executor already treats "no shared layer at all": record it as
  a failed edge with a diagnostic, not a crash.
* **(B) Route it on some grid-backed layer anyway** — effectively what
  the non-tree path already does via `grids.get(preferred, grid)`.

(B) *looks* like the better fix — more nets complete. Both were run to
completion on the production board, same harness, and DRC'd:

| policy | completion | unrouted | segments emitted | DRC unconnected |
|---|---|---|---|---|
| (A) reject | **26.26%** | 73 / 108 | 10,254 | **396** |
| (B) route anyway | 41.59% | 66 / 108 | 33,859 | **398** |

(B) reports **+15.3 points of completion** and **23,605 extra segments**
— and **two more unconnected items**, not fewer. The extra copper lands on
`In1.Cu` and never touches the `F.Cu` pads it was nominally routing to;
via counts are identical (48) in both runs, so nothing bridges the layers
to actually connect anything. `shorting_items` is 199 in both. DRC
run-to-run noise was quantified separately (total violations vary ±40 per
repeat) and `unconnected_items` was confirmed stable to the item across
repeats for both policies — the 396-vs-398 gap is signal, not scatter.

**(B)'s higher completion number was fabricated.** It reports more
"routed" nets while measurably not connecting more copper — the opposite
of what completion is supposed to indicate. (A) was implemented, matching
the executor's own already-tested policy of returning `INCOMPLETE` for an
edge with `no_shared_layer`, and matching `_allow_forced_segments`'s
stated principle: "nothing on this board is worth an honest 'unrouted'
less than a silently unsafe 'routed'."

(A) is also, separately, strictly better than the *old* crashing code on
every input, not merely a tradeoff: the old code took the *first* shared
layer in declaration order and indexed `grids` with it unconditionally —
if a grid-backed shared layer happened to sit second in that order, the
old code raised `KeyError` instead of using it. The new filter walks the
same preference order and takes the first candidate *that has a grid*, so
a net whose pads share `("F.Cu", "In1.Cu")` on a board with only inner
grids now correctly routes on `In1.Cu` where it previously crashed. Any
board that never crashed before is unaffected, because the intersection
is a no-op when every shared layer already has a grid.

## Guidance

### Fix

1. `_shared_pad_layers` extracted as its own function: the terminals'
   shared conductive layers, source-declaration-order first, remainder
   sorted for determinism.
2. `_pick_route_layer` gained a `routable_layers: frozenset[str]`
   parameter and now returns the first shared layer that is *also* a key
   the router has a grid for — never a layer chosen from pad geometry
   alone.
3. `select_routing_grids(occupancy_grids)` extracted in
   `_pipeline_route.py`: primary grid preferred as `"F.Cu"` if present,
   else any grid; alternate preferred as `"B.Cu"` if present, else the
   first grid whose **layer name differs from the primary's actual
   resolved layer** (`candidate.layer_name`, not the literal string
   `"F.Cu"`). Unit-tested directly.
4. Rejected edges now carry a diagnostic distinguishing two causes so
   neither hides inside a generic congestion bucket: `no_shared_layer`
   (a geometry gap — the pads share no conductive layer at all, needing a
   via-aware transition) vs. `no_routable_layer` (a router-configuration
   gap — the pads share a layer, but the router has no grid for it).

### Verification

- `tests/router_v6/`: 2208 passed / 7 failed vs. `main`'s 2194 / 7 — the
  same seven pre-existing failures, +14 new passes from this fix.
- `tests/placer/cp_sat/`: 392 passed / 0 failed vs. `main`'s 392 / 1 (the
  one failure was this bug's target test).
- Non-tree production routing is byte-identical before and after: 41/108,
  38.54% completion, 396 unconnected — confirming the fix touches nothing
  on paths that were already working.
- `TestGridFilterPreservesRoutableWork` pins that the filter never rejects
  an edge some other layer choice could have completed.

## Why This Matters

**The tempting fix (route anyway) reported a better headline number while
measurably making the DRC outcome worse.** Completion rate, read alone,
would have said this was an improvement — 41.59% beats 26.26%. Only
routing the same board both ways and running real DRC against both
surfaced that the extra "completed" work was copper that never touches
the pads it claims to connect. **Ship the honest lower number, not the
fabricated higher one** — a metric that can be inflated by work
disconnected from its own stated purpose is worse than useless, because it
actively rewards the wrong fix.

**A filter that only ever *rejects* cannot make things worse**, which is
what makes (A) safe to prefer even before measuring: the intersection
with `routable_layers` can only remove a layer choice that was already
impossible to route on. Any correctness argument that starts "this is
strictly no worse than before, and here is the proof" is worth making
before reaching for the measurement — the measurement here confirmed
intuition rather than substituting for it.

**Fixing this crash unmasked a second problem it had been hiding**: the
zone/pour regression job died at this exact `KeyError` before ever
reaching `test_zone_pour_production_measurement`, so a stale baseline in
that test (see the companion stale-baseline document) had never actually
run in CI. See
`docs/solutions/best-practices/unmasking-cascades-are-expected-2026-07-29.md`.

## What This Does Not Fix

`no_routable_layer` is a real, now-visible capability gap, not resolved
here: an `F.Cu` SMD pad on this board can only be reached through the
`F.Cu` pour itself or a via down to an inner layer, and the tree executor
has no via-aware layer transition. The honest completion number for
all-pad-tree routing on this board is 26.26%. Raising it requires either
via-aware tree edges, or revisiting whether the outer layers should be
poured at all (`docs/evidence/2026-07-28-stackup-partial-revert.md`).

## When to Apply

- When a router, scheduler, or allocator picks a resource key from one
  side of a two-sided match (here: pad layers) without intersecting
  against what the *other* side (the grid/resource pool) actually has —
  audit every such pick for the same missing intersection.
- When two candidate fixes differ mainly in "how much gets marked done":
  measure both against the same downstream verifier (here: real DRC, not
  just the router's own completion accounting) before trusting the higher
  number.
- When excluding "the other candidate" from a fallback selection: exclude
  by the resolved value already chosen, not by a literal name that may
  never actually appear as a key on the board you're running against.
- After fixing any crash that gates an entire test/CI job: check whether
  a downstream test in the same job was previously unreachable and is now
  running — possibly for the first time in a while — against a baseline
  nobody has re-verified.

## Related

- `docs/solutions/best-practices/stale-absolute-baseline-vs-mutable-board-2026-07-29.md`
  — the zone/pour `260` baseline this fix's own regression run unmasked
- `docs/solutions/best-practices/unmasking-cascades-are-expected-2026-07-29.md`
  — this fix as one of two cascades documented from the same week
- `docs/evidence/2026-07-28-tree-executor-grid-layer-mismatch.md` — full
  measurement detail, including the diagnostic message format and the
  suite-level pass/fail comparison against `main`
- `docs/evidence/2026-07-28-stackup-partial-revert.md` — why outer layers
  are classified `plane` in the first place, and the 12x completion cost
  of the alternative
- PR #386 (`b39b382d`) — the fix this document covers
