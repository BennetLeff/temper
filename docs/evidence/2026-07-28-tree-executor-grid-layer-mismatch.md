# `KeyError: 'F.Cu'` — the tree executor picked a layer nobody built a grid for

<!-- provenance: commit=65fc5df7cfee43eca1a3a6cfe1b81f235610aea2 dirty=true -->

**Date:** 2026-07-28
**Board:** `pcb/temper.kicad_pcb` (all-pad-tree + zone pours)
**Fixes:** `terminal_tree_execution.py`, `_pipeline_route.py`, `_astar_reconstruct.py`

## The crash

```
router_v6/_astar_reconstruct.py:342: in attempt_route
router_v6/terminal_tree_execution.py:108: in execute_terminal_tree
E   KeyError: 'F.Cu'
```

`terminal_tree_execution.py:108` was `active_grid = grids[route_layer]`, and
`route_layer` came from `_pick_route_layer`, which computed the shared layer
from the two pads' `layer_names` alone and never asked which layers actually
have an occupancy grid.

## Root cause, traced

Every link measured on the production board, not inferred:

1. `pcb/temper.kicad_pcb` pours per-net copper on `F.Cu`/`B.Cu`, so
   `io/_parse_board.py:264-272`'s zone heuristic classifies both **outer**
   layers as `plane`. This is deliberate and evidence-backed — see
   `docs/evidence/2026-07-28-stackup-partial-revert.md`; forcing them to
   `signal` instead cost 12× completion.
   Measured stackup: `[('F.Cu', 'plane'), ('In1.Cu', 'mixed'), ('In2.Cu',
   'mixed'), ('B.Cu', 'plane')]`.
2. `router_v6/routing_space.py:85` builds routing spaces only for
   `signal`/`mixed` layers, and `occupancy_grid.py:517` builds one grid per
   routing space. Measured: `occupancy_grids keys: ['In1.Cu', 'In2.Cu']`.
3. `router_v6/terminal_extraction.py:63` gives an SMD terminal its declared
   pad layer. Measured: `PAD LAYERS: ['F.Cu']` — correct, that is where the
   pad physically is.
4. `router_v6/terminal_tree_execution.py:42-61` intersected (3) with (3) and
   returned `'F.Cu'`; `grids` only ever held (2). **`KeyError`.**

A second, independent defect sat next to it. `_pipeline_route.py:546-548`
selected the alternate grid by excluding the literal name `"F.Cu"` rather than
the primary grid's actual layer:

```python
fcu_grid = grids.get("F.Cu") or next(iter(grids.values()))          # -> In1.Cu
bcu_grid = grids.get("B.Cu") or next(g for n, g in grids.items()
                                     if n != "F.Cu")                 # -> In1.Cu (!)
```

On a plane-outer board both fall through to the *same* grid, so the router was
handed one layer twice and `In2.Cu` never reached pathfinding at all. Measured
before: `primary grid layer: In1.Cu / alternate grid layer: In1.Cu`.

## The judgement call, and how it was settled by measurement

Two candidate behaviours for an edge whose pads share only grid-less layers:

* **(A) reject the edge** — record it as failed, the way the executor already
  handles pads with no shared layer at all.
* **(B) route it on some grid-backed layer anyway** — what the non-tree path
  effectively does via `all_grids.get(preferred_layer, grid)`.

(B) reports more completion, so (A) looks like a masking fix. It is not.
Both were run end to end on the production board, identical harness:

| policy | completion | unrouted | segments emitted | DRC unconnected |
|---|---|---|---|---|
| (A) reject | **26.26%** | 73 / 108 | 10,254 | **396** |
| (B) route anyway | 41.59% | 66 / 108 | 33,859 | **398** |

(B) buys **+15.3 points of reported completion, 23,605 extra segments, and two
*more* unconnected items.** The extra copper lands on `In1.Cu` and never
touches the `F.Cu` pads — via counts are identical (48) in both, so nothing
bridges the layers. `shorting_items` is 199 in both.

DRC run-to-run noise was quantified (3 repeats per file): total violations
vary ±40, but `unconnected_items` is stable to the item — 396 for (A) on every
run, 398 for (B) on every run. The 2-item gap is signal.

This also matches the repo's existing, tested policy: the executor already
returns `INCOMPLETE` "rather than routing on the wrong layer"
(`test_multi_layer_tree_routing.py::test_no_shared_layer_returns_incomplete`),
and `_allow_forced_segments` states the principle outright — "nothing on this
board is worth an honest 'unrouted' less than a silently unsafe 'routed'".

**(A) is implemented.** It cannot lower completion by construction: the
intersection can only reject a layer with no occupancy grid, which the router
cannot route on under any policy. It never rejects an edge some other layer
choice could have completed — pinned by
`TestGridFilterPreservesRoutableWork`.

In fact the filter is strictly better than the old code on every input, not
merely equal. The old version took the *first* shared layer in source
declaration order and indexed `grids` with it; if a grid-backed shared layer
sat second in that order, the old code raised `KeyError` instead of using it.
The new version walks the same preference order and takes the first candidate
that has a grid, so a net whose pads share `("F.Cu", "In1.Cu")` on a board with
only inner grids now *routes on `In1.Cu`* where it previously crashed. Any
board that did not crash before is unaffected — when every shared layer has a
grid the intersection is a no-op.

## The unchanged configuration, as a control

`test_temper_production_board_routing.py::test_route_pcb_production_board`
routes the same board *without* all-pad trees, so it never reached the crash.
Its numbers are identical before and after — the fix touches nothing on paths
that were already working:

| | routed | completion | DRC unconnected | DRC violations |
|---|---|---|---|---|
| `origin/main` | 41 / 108 | 38.54% | 396 | 1755 |
| this branch | 41 / 108 | 38.54% | 396 | 1785 |

(The violation delta is inside the ±40 run-to-run band measured above; the
routed `.kicad_pcb` is unchanged.)

## Not a silent swallow

A rejected edge now carries a diagnostic naming both sides of the mismatch,
and the two causes are reported separately so neither hides inside the
congestion bucket:

```
✗ hb.gate_hs.driver-p2 INCOMPLETE: no_routable_layer: pads share ['F.Cu']
    but no occupancy grid exists for any of them; grids=['In1.Cu', 'In2.Cu']
✗ safety-line INCOMPLETE: no_shared_layer: source=['In1.Cu', 'In2.Cu']
    target=['F.Cu'] grids=['In1.Cu', 'In2.Cu']
```

`RoutingFailureReport.failure_reason` gets `no_routable_layer`, so
`print_failure_analysis()` counts these separately from `no_path`.

## What this does *not* fix

`no_routable_layer` is a real capability gap, now visible instead of fatal: an
`F.Cu` SMD pad on this board can only be reached through the `F.Cu` pour or a
via down to an inner layer, and the tree executor has no via-aware transition.
The honest number is 26.26%. Raising it requires either via-aware tree edges or
the board decision left open in
`docs/evidence/2026-07-28-stackup-partial-revert.md` (should the outer layers
be poured at all).

## Suites

`tests/router_v6/`, same machine, `origin/main` in a second worktree:

| | passed | failed | skipped | xfailed |
|---|---|---|---|---|
| `origin/main` | 2194 | 7 | 15 | 23 |
| this branch | 2208 | 7 | 15 | 23 |

The seven failures are the *same* seven in both runs — four
`test_astar_3d_production_scale_spike` production cases (already recorded as
outstanding in `2026-07-28-stackup-partial-revert.md`), `test_dfm_interaction`,
`test_temper_production_board_routing`, and a missing committed U8 measurement
JSON. None are introduced here. The +14 passes are this branch's new tests.

## UNVERIFIED

* Recovering `In2.Cu` as a distinct alternate grid did not change this board's
  output — the routed `.kicad_pcb` is byte-identical before and after, because
  every shared-layer pick still resolves to `In1.Cu` first. It is fixed as a
  correctness defect, not on measured benefit.
* Zone-filled DRC (`pcbnew.ZONE_FILLER`) was not run locally; `pcbnew` is not
  importable from `/usr/bin/python3` on macOS. The numbers above are unfilled
  `kicad-cli pcb drc`, which is comparable across variants but higher in
  absolute terms than CI's filled runs.
* `test_astar_3d_production_scale_spike`'s remaining failures were not
  re-diagnosed here, though the prior evidence doc records them once failing
  with this same `KeyError: 'F.Cu'`.
