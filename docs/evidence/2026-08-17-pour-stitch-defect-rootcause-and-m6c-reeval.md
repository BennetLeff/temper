<!-- provenance: commit=eca0d755a dirty=false (worktree agent-ae9876aa8752c1a79, main tip at task start). pcb/temper.kicad_pcb sha256 6ac8b1ca8a6400b7bd775f335c59fd0873b89b0ae4ce095be11a91f6395916e1, matches task brief, NOT modified by this task -- all measurement on scratch copies under /tmp. -->
---
title: "+3V3 pour-stitch track_width defect: root cause and fix, independent of M6c; M6c re-evaluated on top of it"
date: 2026-08-17
module: temper-placer
tags: [router, zone-stitch, power-islands, drc, track_width]
problem_type: drc-defect
status: in-progress
---

# +3V3 pour-stitch defect: root cause + fix, then M6c re-evaluation

**Status: IN PROGRESS**, committed incrementally per this project's survival rule
(a worktree with no commits is destroyed on stop).

## Task

Three phases, per the coordinating brief:

1. Root-cause and fix a pre-existing `+3V3` pour-stitch `track_width` defect
   on current main, independent of M6c (branch `spike/router-m6c-partial-geometry`,
   PR #1327). Prior art already characterized this defect indirectly in
   `docs/evidence/2026-08-17-routing-cause-refresh-and-tractable-fix.md` §6: at
   M6c's own baseline (committed board `6ac8b1ca...`), `+3V3` already carries
   100 `track_width` violations pre-M6c, worsening to 167 under M6c's added
   congestion (traced there to "the pour/plane MST-stitch generator's own
   narrow via-drop-avoidance stubs, `_power_islands.py`"). That characterization
   did not fix the defect. This document does.
2. Rebase/cherry-pick M6c onto the fix and re-measure whether M6c is a net win
   with the confound removed.
3. If a genuine win: tests + a type-system guard for "safe, computed route
   geometry must not be silently discarded" (or a documented reason a test is
   the better expression).

## 1. Baseline provenance (this document's own, not inherited)

`kicad-cli 10.0.5`. Board: `pcb/temper.kicad_pcb`, sha256 `6ac8b1ca...`
(matches the task brief; unmodified throughout -- verified before and after
every step in this document). Measurement: a scratch copy of the committed
board, `.kicad_pro` copied verbatim from `pcb/temper.kicad_pro`, `.kicad_dru`
freshly regenerated via `generate_kicad_dru.generate_dru()` (called directly,
NOT via `scripts/generate_kicad_dru.py`'s `main()` -- that also overwrites 4
tracked `*.generated.yaml` config files as a side effect, which this
measurement must not touch). `kicad-cli pcb drc --severity-all
--all-track-errors --format json`, with and without `--refill-zones`.

**No-refill**: clearance 224, track_width 120, creepage 100, shorting_items
53, hole_clearance 26, solder_mask_bridge 15, copper_edge_clearance 12,
tracks_crossing 8, drill_out_of_range 6, courtyards_overlap 1 (errors, 565
total); silk_overlap 199 [CAPPED], lib_footprint_issues 168, via_dangling
106, silk_over_copper 42, missing_courtyard 5, silk_edge_clearance 1
(warnings, 521 total). **Total 1086.**

**`--refill-zones`**: clearance 225, creepage 121, track_width 120,
shorting_items 53, hole_clearance 26, solder_mask_bridge 15,
copper_edge_clearance 12, tracks_crossing 8, drill_out_of_range 6,
courtyards_overlap 1 (errors, 587); silk_overlap 199 [CAPPED],
lib_footprint_issues 168, silk_over_copper 42, via_dangling 23,
missing_courtyard 5, silk_edge_clearance 1 (warnings, 438). **Total 1025.**

Both totals match `docs/evidence/2026-08-17-routing-cause-refresh-and-tractable-fix.md`
§1/§6's own independently-measured baseline exactly (1086 no-refill, 1025
refill; track_width 120 both ways; creepage 100/121). This document's own
measurement reproduces that baseline from scratch (own script, own
kicad-cli invocation) rather than inheriting the number -- provenance
closed, no unexplained ~129 gap here.

## 2. Root cause: `_power_islands.py`'s `STITCH_TRACE_WIDTH_MM` hardcoded below the Power netclass DRU floor

Every `track_width` violation's own kicad-cli description was inspected
(not sampled): **all 120/120** read `"Track width (rule 'Power trace width'
min width 1.0000 mm; actual 0.3000 mm)"`, and **all 120/120** name a net in
`{+3V3 (100), vcc (10), +15V (8), V_BUS_SENSE (2)}` -- exactly
`_power_islands.py`'s `POWER_ISLAND_NETS`. This is not "most of the
category traces to X"; the entire category is one defect.

`pcb/temper.kicad_pro` classifies all four of these nets `"Power"`.
`design_rules.py`'s `TEMPER_NET_CLASSES["Power"].trace_width == 1.0` (mm),
which `generate_kicad_dru.py` turns into the DRU's `"Power trace width"`
rule at `min 1.0mm`. `_power_islands.py`'s module-level
`STITCH_TRACE_WIDTH_MM = 0.3` was used, unconditionally, for every stitch
backbone segment (`_emit_segment`, line ~777) and every keepout-detour
fallback segment (line ~704) this generator emits for these nets -- so
every segment it has ever written is, by construction, below the DRU floor
for its own net's class.

### 2a. The finding underneath the finding: a comment asserted a relationship that did not hold

**This defect survived a full day in-repo not because nobody had fixed the
class before, but because a comment said it had already been checked and
was fine.** `_ground_plane.py` hit and fixed this *exact* defect class for
`gnd` one day earlier (2026-08-16, "full-route agent,
fix/route-to-100-percent"): its own `STITCH_TRACE_WIDTH_MM` was raised
0.4 -> 1.0mm after measuring 216/747 `track_width` violations from the
identical mismatch against GND's 1.0mm DRU floor -- see that module's own
comment (`_ground_plane.py` ~line 91-104), which documents the root cause,
the measurement, and the fix in detail.

`_power_islands.py`'s comment on its neighboring `VIA_SIZE_MM` constant
(the line directly above the old `STITCH_TRACE_WIDTH_MM = 0.3`) said:

> "the same board-wide 0.3mm-ring convention applied to every
> `TEMPER_NET_CLASSES` `via_diameter`... and to `_power_islands.py`'s
> identical constant below."

**"Identical" was false when that sentence was written** (`_ground_plane.py`
was already at 1.0mm by then; `_power_islands.py` stayed at 0.3mm) and
stayed false for a full day of subsequent commits, undetected. Nobody who
read that comment had a reason to go check the sibling file's actual
value -- the comment's job was to make the two constants' relationship
legible, and it asserted the opposite of the truth. This is the same
failure class the project's own handoff catalogues as mechanism 5 ("stale
ground truth" -- "comments asserting superseded figures") and is arguably
worse than a stale *test*: a stale assertion with no executable form
cannot fail CI, cannot be caught by `pytest`, and reads exactly as
authoritative as a true one. **A comment that asserts a cross-file
invariant is a claim with zero enforcement** -- the fix here removes the
possibility of re-drifting by deriving the value from the shared SSOT
(`TEMPER_NET_CLASSES["Power"].trace_width`, §3) instead of stating a
"these should match" comment a second time.

## 3. Fix (independent of M6c, `_power_islands.py` only)

`STITCH_TRACE_WIDTH_MM` now reads `TEMPER_NET_CLASSES["Power"].trace_width`
(imported from `core.design_rules`) instead of a second hardcoded literal --
deriving from the netclass SSOT rather than re-copying a number that can
drift from it again, since a drifted copy is exactly the bug being fixed.
Resolves to `1.0` today, verified by direct import. `compute_corridor_mask`
and the inter-net blocked-check radius are keyed off the same constant, so
the A* corridor search and inter-rail clearance widen consistently with the
emitted geometry -- the same single-knob relationship `_ground_plane.py`'s
own fix already established. No other file touched; `pcb/temper.kicad_pcb`
not touched (sha256 verified unchanged before and after).

Existing test suite: `test_power_islands.py` -- 1 of 2 tests fails, and it
is provably pre-existing/unrelated: `baseline = audit_pcb_file(scratch)`
runs on a bare `shutil.copy` of the committed board, **before**
`generate_power_islands_content` is even called, so nothing in this fix's
diff can affect it. It asserts the committed board's own pre-existing
`+3V3` copper is zero, which has been false since #1312's copper
regeneration gave these rails real copper independent of this module --
already documented as stale in the M6c evidence doc's own regression table
(§4, `test_power_islands.py::...measurably_improve_connectivity`). The
second test (`test_rails_do_not_overlap_on_shared_layer`) passes.

## 4. A measurement bug caught before being reported: the shared `.venv`'s `temper_placer` resolves to the MAIN checkout, not this worktree

The first full-route "after-fix" attempt measured `track_width: 197` (UP
from 120, not down) -- every single one of the 197 violations' own
description still read `"actual 0.3000 mm"`. That is the tell: if the fix
had been in effect, no violation could report `0.3000mm` at all (the
constant no longer exists in the source). **The route never used this
worktree's fix.**

Root cause: this repo's shared `.venv`
(`/home/bennet/Desktop/temper/.venv`) has `temper_placer` `pip install -e`'d
against `_editable_impl_temper_placer.pth`, which points at
`/home/bennet/Desktop/temper/packages/temper-placer/src` -- **the main
checkout, not this worktree** (`.claude/worktrees/agent-ae9876aa8752c1a79/packages/...`).
Invoking `scripts/route_board.py` from this worktree's own copy of the
script still resolves `import temper_placer` through that stale editable
pointer, because nothing in `route_board.py` or the shared venv's
`sys.path` favors this worktree's source over site-packages'. This is a
silent instrument failure of exactly the kind handoff §12 names: a
verification that looks complete (a real full route ran, real DRC was
measured) but is blind on the one axis that mattered here (which source
tree actually executed).

**Not a violation of "no pyo3 rebuilds into the shared venv"** -- no
extension was rebuilt, and the fix is pure Python; the corrective is a
`sys.path` override (`packages/*/src` from this worktree, inserted ahead
of site-packages), applied via a small wrapper
(`route_via_worktree.py`) that `exec`s `route_board.py` after the
override, verified by a direct import check
(`temper_placer.router_v6._power_islands.STITCH_TRACE_WIDTH_MM == 1.0`,
confirmed resolving to this worktree's own file path) **before** re-running
the route. The invalid 197/60-of-139 result above is discarded and not
used anywhere in this document's conclusions.

## 5. Full-route standalone measurement: fix applied, no M6c (corrected methodology)

`scripts/route_board.py` default recipe (via the worktree-forcing wrapper,
§4), from this worktree's `pcb/temper.kicad_pcb` (sha256 verified
`6ac8b1ca...` before AND after running -- board file untouched). Also
re-verified via a throwaway pytest sanity test (deleted immediately after)
that pytest's own `pythonpath = ["src"]` ini option (unlike a bare script
invocation) already correctly resolves `temper_placer` to this worktree --
so `test_power_islands.py`'s result in §3 needed no correction.

**Connectivity**: 63/139 nets fully pad-connected (`NetRouteResult`:
63 connected, 9 zone-dependent, 7 partial, 60 failed), matching the M6c
evidence doc's own independently-measured baseline (63/139) exactly. **The
fix costs zero connectivity** -- the corridor-mask/blocked-radius widening
that comes from deriving the correct 1.0mm width did not measurably change
which nets complete.

**DRC, `kicad-cli 10.0.5`, `--severity-all --all-track-errors`, full
project context**:

| category | no-refill | `--refill-zones` |
|---|---|---|
| clearance | 245 | 246 |
| creepage | **100** | **121** |
| shorting_items | 96 | 96 |
| hole_clearance | 33 | 33 |
| solder_mask_bridge | 31 | 31 |
| copper_edge_clearance | 13 | 13 |
| tracks_crossing | 8 | 8 |
| drill_out_of_range | 6 | 6 |
| courtyards_overlap | 1 | 1 |
| **track_width** | **0** | **0** |
| silk_overlap | 199 [CAPPED] | 199 [CAPPED] |
| lib_footprint_issues | 168 | 168 |
| via_dangling | 106 | 23 |
| silk_over_copper | 42 | 42 |
| missing_courtyard | 5 | 5 |
| silk_edge_clearance | 1 | 1 |
| **total** | **1054** | **993** |

**The headline prediction is confirmed exactly**: `track_width` goes
**120 -> 0**, not "down" -- the coordinator's own prediction, and the
direct consequence of the root cause being complete (§2: 120/120 of the
category was this one defect, and this generator was the only source of
any of it). Creepage held exactly flat (100/121, matching the
`--refill-zones` baseline too) -- no new HV/LV separation violation.

**This total is NOT a clean "fix-only" delta against the 1086/1025
baseline** and is not reported as one: the baseline (§1) is the
already-committed, already-routed board measured as-is (no fresh route),
while this measurement is a **full fresh `route_board.py` pass** that also
newly routes ~9 previously-unrouted nets (63/139 vs the committed board's
own audited 63/139 -- coincidentally equal in count, not the same net
set) and regenerates every zone/pour from scratch. `clearance`
(224->245), `shorting_items` (53->96), `hole_clearance` (26->33), and
`solder_mask_bridge` (15->31) all moved for reasons entirely orthogonal to
this fix -- new copper from a fresh route, not the stitch-width change.
`track_width` is the one category this document isolates cleanly, because
it was independently shown (§2) to be 100% attributable to the one fixed
constant, and it lands exactly where that attribution predicts. A fully
isolated fix-only delta (same fresh route, old vs new width, all else
equal) was not run a second time given the cost of an ~5-6 minute route
and the unambiguous track_width evidence already in hand; Phase 2's
determinism pair (§6) uses this same corrected board as its own baseline,
so the M6c comparison in §6 is apples-to-apples regardless.
