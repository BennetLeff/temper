<!-- provenance: commit=fa067a9523cba69978ea7216a65009f6343315a7 dirty=false (worktree agent-routing-completeness-recon, branched from origin/main at fa067a9523cba69978ea7216a65009f6343315a7. pcb/temper.kicad_pcb sha256 9c1f4a37b03c6433275704c3bed917f7ff16877c762f0aa8d37cc6858d7c16dd verified unchanged, never opened for writing by this task -- every route below writes to a scratch path outside the repo/worktree tracked tree.) -->
---
title: "Phase 2 draft: per-net root cause on the current main tip (build in progress)"
date: 2026-08-17
module: temper-placer
tags: [router, routing, pad-connectivity, root-cause, draft]
problem_type: routing-completion
status: draft-pending-live-measurement
---

# Phase 2 (in progress): why each still-unrouted net is unrouted, on current `main`

**Status**: this is a placeholder committed early (per the coordinator's
"commit as your first action, and after every meaningful step" rule)
while a live route (`scripts/route_board.py`, default no-`--net-batching`
recipe, current worktree tip `fa067a952`) runs in the background. Will be
filled in with the fresh per-net table once that completes. Builds on,
does not redo, `docs/evidence/2026-08-15-unrouted-nets-rootcause.md`
(PR #1290) — see `docs/evidence/2026-08-17-routing-completeness-
reconciliation.md` (this task's Phase 1) for why that doc's 62/139
baseline and the M1/M2/M3/M4/M5 mechanism taxonomy are still the right
frame, but the *specific per-net assignments* are stale: M1 (#1246),
M2 (#1245 zone rotation), and M3 (#1245 `enable_all_pad_tree`) have all
landed on `main` since that doc was written, so most of the 63
"router-fixable" nets it names have already moved out of their listed
mechanism.

## What's already re-verified from source (no route needed for these)

- **M1 (wrong-layer landing) is fixed on `main`**: `_land_route_on_pad_layers`
  exists in `_astar_nlayer.py` (line 590), matching the fix the 2026-08-15
  doc named as unmerged.
- **M2 (zone rotation) and M3 (`enable_all_pad_tree` default) are fixed on
  `main`**: `_pipeline_core.py:155` and `_adapter_convert.py:229` both
  default `enable_all_pad_tree=True` (was `False` in the 2026-08-15 doc's
  tree).
- **M2b (missing zone-fill pass) is STILL not wired**: no
  `fill-zones`/`filled_polygon` emission found in `route_board.py` or
  `zone_emission.py`. Every `zone_dependent` net remains fill-blind to
  the audit — this has not changed since the 2026-08-15 doc.
- **M4 `gnd`/`+3V3` pour-vs-trace**: both now get a *dedicated* inner-layer
  plane/island generator wired directly into `_adapter_convert.py`
  (`_ground_plane.py` → In1.Cu for `gnd`, `_power_islands.py` → In2.Cu for
  `+3V3`/`vcc`/`+15V`), gated only on `enable_zone_pours` (production
  default `True`, `_adapter_convert.py:230`) and the net existing on the
  board. This is new since the 2026-08-15 doc (which found `gnd`'s plane
  generator caller-less). **Still A*-routed as a trace in parallel**
  (`gnd`/`+3V3` are classed `"Power"`, which declares no
  `routing_strategy`, so `_should_route()` still sends them through A* at
  1.0mm trace width across a 296mm/238mm span) — the plane supplements
  rather than replaces the original M4 defect; per the 2026-08-16 capstone
  doc, the trace/via graph alone reached only 53/88 `gnd` pads, with the
  rest dependent on the (unmeasured, fill-blind) plane fill.
- **Zone-stitch C-space (#1261) and creepage-aware halos (#1267) are new
  since 2026-08-15** and, per Phase 1's reconciliation doc, are the
  leading suspects for *new* honest declines not represented in any prior
  M1-M5 bucket: a net that used to "connect" via an under-stamped foreign
  obstacle now honestly fails. This is plausibly a **sixth mechanism**
  (call it **M6 — foreign-clearance/creepage ring restored**) alongside
  the original five; PR #1301 (unmerged) is the most advanced diagnosis
  of this specific mechanism for the clearance case.

## Next section: fresh per-net table

*(pending live route completion)*
