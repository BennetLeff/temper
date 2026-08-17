# Via-vs-inner-track clearance + clearance-family measurement (2026-08-16)

<!-- provenance: filled in after measurement -->

## Summary

Two routing fixes for the remaining clearance and shorting violations on the
6-layer N-layer A* routed board:

1. **Via-vs-inner-track clearance (Fix 1)**: every via-placement site in the
   N-layer A* checked the via's clearance on AT MOST ONE layer, so a via's
   barrel landed inside a foreign track on an inner pierced layer (the
   residual shorting_items). The fix (`astar_core._via_placement_halo_free`)
   verifies the via's centre cell AND its extra barrel extent on EVERY layer
   the via physically pierces, fail-closed.
2. **Clearance family (Fix 2)**: measured after Fix 1 — see §5.

## Branch / base

- Branch: `fix/via-clearance-and-clearance-family`
- Base: `origin/main` @ `593d9ab24`
- Commit: `d5308c535` (cherry-picked from `fix/via-clearance-and-fab-rules`
  `751e7b4e6`, conflict-resolved against #1267's creepage-halo stamp comment)

## Root cause (Fix 1)

Quote from the 2026-08-16 route-to-100 evidence (§5 item 5): "shorting_items
11 — ALL are the N-layer A* machinery's own via-vs-track shorts on
In3.Cu/In4.Cu... this is a DIFFERENT bug class from this task's (the A*
router's own via placement does not consult the width-aware C-space for the
via's inner-layer barrel clearance against tracks routed on other layers —
#1249 fixed track halos, not via-vs-inner-track)".

The three via-placement sites:

| site | pre-fix check | layer span checked |
|---|---|---|
| tier-3 transition (`_astar_search_3d`) | `other_grid.is_free(x, y)` | destination layer ONLY |
| tier-2 anchor (`_astar_route_nlayer`) | none | none |
| landing via (`_attempt_pad_layer_landing`) | `grid.is_free` on pad layer | pad layer ONLY |

A through via F.Cu↔B.Cu therefore landed with its In3.Cu/In4.Cu barrel inside
another net's track, and the width-aware family grids could not prevent it
because the placement check never consulted the inner layers' grids.

## The fix (details)

`astar_core._via_placement_halo_free` — on every layer the via pierces
(`_via_span_layers` over `VIA_SPAN_LAYER_ORDER = (F.Cu, In3.Cu, In4.Cu, B.Cu)`):

- the via's centre cell is free (or owned by the via's own net), and
- the via's extra barrel extent beyond the net's track half-width
  (`max(0, via_diameter/2 - trace_width/2)`) is free as a disc.

Together: `d(via_center, F_centerline) >= v_d/2 + w_F/2 + max(cl_F, C,
creepage)` — edge-to-edge gap >= the DRC pair floor, matching the width-aware
family design's track-vs-track guarantee. The -1 creepage halos (#1267) are
blocked cells, so the check also enforces creepage automatically.

Also in this commit (fab-rule fixes, measured on the 2026-08-16 route):
- annular_width 68: HighVoltageSignal via 0.8/0.4 → 1.0/0.4 (0.3mm ring >=
  min_via_annular_width 0.254)
- holes_co_located 60: dedupe identical via positions + drop vias at the
  net's own THT pad centres
- via_dangling 44: gnd drop via skipped fail-closed with its blocked stub

## Tests

- new `test_astar_via_span_clearance.py` (5 tests): span-layer enumeration,
  halo rejection on inner pierced layers, own-net tolerance, tier-3 refusal/
  allowance
- `test_astar_route_multilayer_via_fallback.py` (7 tests)
- `test_astar_3d_production_scale_spike.py` (8 tests)
- full `tests/router_v6/`: 6809 passed; the 24 failures are byte-identical to
  plain main (verified by running the same modules in the main worktree) —
  zero new failures

## Measurement (before/after)

... (filled in after routes complete)
