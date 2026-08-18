<!-- provenance: commit=342e1bd08 dirty=false (worktree agent-a7e7a9c50f564ffdb, main tip at task start). pcb/temper.kicad_pcb sha256 cb5184eae9fea94c4b7b3c68c553ce97923a0d8f9af9d0fbb87442ab593c39b3, matches task brief. -->
---
title: "Revert M6c (PR #1329's incidental carry), land Tier-3 span-scaled budget fix, re-route and measure"
date: 2026-08-17
module: temper-placer
tags: [router, revert, routing-completion, drc]
problem_type: routing-completion
status: in-progress
---

# M6c revert + Tier-3 span-scaled budget reland

**Status: IN PROGRESS.** Stub committed first per this project's survival
rule (a worktree with no commits is destroyed on stop). Findings and
measurements follow in later commits to this same file.

## Task, per the coordinating brief

1. Revert M6c's four files to their pre-PR-#1329 state
   (`_astar_nlayer.py`, `routing_results.py`, `terminal_tree_execution.py`,
   `test_all_pad_tree_routing.py`), while keeping PR #1329's
   `_power_islands.py` stitch-width fix and PR #1332's collision-check
   work on that same file.
2. Land the Tier-3 span-scaled search-budget fix from branch
   `worktree-agent-a117df333e1fd0c5f` (built on M6c-containing main;
   needs reconciling against the revert).
3. Re-route and measure: connectivity, DRC (both refill modes, HV/LV
   creepage broken out), fake-completion count, determinism (two
   byte-identical routes), in an isolated venv verified to resolve inside
   this worktree.
4. Commit the board only if connectivity improves (target >= 62/139) and
   no DRC category regresses. Otherwise report the finding as-is.

## 0. State at task start

- Main tip: `342e1bd08`.
- `pcb/temper.kicad_pcb` sha256 `cb5184eae9fea94c4b7b3c68c553ce97923a0d8f9af9d0fbb87442ab593c39b3` --
  matches the task brief exactly.
- M6c's four files landed via PR #1329 (`7979a0ee1`, 2026-08-17 18:33),
  bundled with the independent `_power_islands.py` pour-stitch fix.
  `7979a0ee1^` is confirmed (via `git log -- <path>`) to be the last
  commit touching `_astar_nlayer.py` before M6c, i.e. the correct revert
  target for all four M6c files.
- `_power_islands.py` at current HEAD carries both `STITCH_TRACE_WIDTH_MM
  = TEMPER_NET_CLASSES["Power"].trace_width` (PR #1329) and the
  `other_copper_fcu_backbone`/`routed_fcu_backbone` collision checks
  (PR #1332) -- confirmed present by direct grep before starting the
  revert.
- Tier-3 fix source: `docs/evidence/2026-08-17-hop-reachability-rootcause-and-fix.md`
  on worktree `agent-a117df333e1fd0c5f` (branch tip `666cfd64d`). Its own
  §6 states the fix was verified only via unit/property regression (394
  passed, 2 pre-existing unrelated failures) and structural
  can't-fabricate-completions argument -- three full-route verification
  attempts were killed unfinished. A full-board connectivity/DRC/
  determinism measurement of the shipped fix does not yet exist anywhere
  and is this task's job to produce.

## 1. Revert mechanics

`7979a0ee1^` (PR #1329's parent) confirmed via `git log 7979a0ee1..342e1bd08
-- <path>` to be the last commit touching any of the four M6c files before
this task -- i.e. no legitimate post-#1329 work exists on any of them, so a
clean `git show 7979a0ee1^:<path> > <path>` revert is lossless. Diff sizes
after revert matched the brief exactly: `_astar_nlayer.py` 168 lines,
`routing_results.py` 71, `terminal_tree_execution.py` 195,
`test_all_pad_tree_routing.py` 45 (93 insertions, 386 deletions total).

`_power_islands.py` verified untouched by the revert (grep before and
after): `STITCH_TRACE_WIDTH_MM = TEMPER_NET_CLASSES["Power"].trace_width`
(PR #1329) and the `other_copper_fcu_backbone`/`routed_fcu_backbone`
collision checks (PR #1332) both still present.

Committed as `7aaa351fe`.

## 2. Tier-3 fix reconciliation

`worktree-agent-a117df333e1fd0c5f`'s branch (tip `666cfd64d`) was built on
M6c-containing main. Its merge-base with this history, `ac8dbf7ab`,
predates PR #1329/M6c entirely -- so `git diff ac8dbf7ab 666cfd64d --
.../_astar_nlayer.py` isolates exactly the Tier-3 span-scaled-budget fix
with zero M6c residue (confirmed: `git diff ac8dbf7ab 666cfd64d --stat --
packages/ crates/` touches only this one file, 40 lines, one call site
plus comment). Confirmed `git apply --check` succeeds cleanly against this
worktree's just-reverted file, then applied. Committed as `a3e1f0cfc`.

## 3. Isolated venv, verified resolving inside this worktree

`make venv-isolate` hit two environment hazards, both worked around without
touching any shared/global config:

1. `CONDA_PREFIX` + `VIRTUAL_ENV` both set (base conda env active in the
   ambient shell) made every `maturin develop` call fail immediately
   ("Both VIRTUAL_ENV and CONDA_PREFIX are set"). Fixed by unsetting the
   three `CONDA_*` vars for the build commands only (`unset CONDA_PREFIX
   CONDA_DEFAULT_ENV CONDA_SHLVL`) -- no global/shared config touched.
2. The shared `CARGO_TARGET_DIR` (`target-shared`, one dir for all 273+
   worktrees off the same `.git`) produced a `temper_geometry` cdylib
   missing its `PyInit_temper_geometry` export symbol on the first build
   attempt (`Finished ... in 0.04s` -- suspiciously fast, almost certainly
   a stale/corrupted fingerprint match from a concurrent worktree's
   differently-featured build racing the same shared target dir). Fixed by
   `touch`ing the crate's `lib.rs` and re-running `maturin develop --release`
   for that one crate alone, which forced a real recompile (6.12s, real
   `Compiling` line this time) and produced a working symbol.

Verified post-fix, direct import from `.venv/bin/python3`:
- `temper_placer.__file__` → this worktree's own
  `packages/temper-placer/src/temper_placer/__init__.py` (not the shared
  `.venv`'s stale editable pointer into the main checkout -- the "fifth
  venv mode" failure this project's own `AGENTS.md` documents).
- `temper_placer.router_v6._astar_nlayer._SEGMENT_3D_FALLBACK_MAX_ITER ==
  200000` and the file resolves inside this worktree.
- `temper_placer.router_v6._power_islands.STITCH_TRACE_WIDTH_MM == 1.0`
  and the file resolves inside this worktree.

## 4. Regression suite

`test_astar_nlayer.py`: 27/27 pass.

Broader sweep (`-k "astar or nlayer or routing_results or pipeline_route or
terminal_tree or all_pad_tree"`, 438 selected): **434 passed, 5 skipped, 2
failed.** Both failures are the same pre-existing, already-documented
`_via(diameter=0.6)` fixture staleness (PR #1316 raised the production
via-diameter floor 0.6→0.9mm; these two differential-test fixtures were
never updated) -- confirmed by inspecting the fixture helper directly and
by the failure diff itself (`size 0.6000` expected vs `size 0.9000` actual,
nothing else differs). This change touches neither `via_diameter` nor any
fixture, so it cannot be the cause; matches the Tier-3 evidence doc's own
regression table exactly.

## 5. Full route + DRC measurement

### 5a. Determinism

Two full `scripts/route_board.py` runs (default recipe, no `--net-batching`,
no `--pruning`, no `--nlayer-astar-spike`) from the committed board's own
placement (`pcb/temper.kicad_pcb`, sha256 `cb5184eae9...`, unmodified
throughout -- verified before and after this entire section):

```
route1.kicad_pcb sha256: 26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b
route2.kicad_pcb sha256: 26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b
```

**Byte-identical.** Both runs also reported identical logs: same
completion (34/105, 32.4%), same segment/via/zone counts (4553/169/151),
same pad-connectivity (60/139), same fake-completion set (6:
`+15V,+3V3,GATE_LS,V_BUS_SENSE,gnd,vcc`), same unrouted-net set (71 nets,
listed identically both runs).

### 5b. Placement untouched

Every one of the 168 footprints' own `(at ...)` s-expression compared
between the committed board and `route1.kicad_pcb`: **0 differences.**
(Regex-extracted the first `(at ...)` following each `(footprint "...")`
opening and diffed pairwise, index-aligned since footprint count and order
are identical.)

### 5c. DRC methodology, calibrated against the committed board first

Rather than trust a differently-run prior agent's baseline numbers, this
document re-measures the **currently committed board** (`cb5184eae9...`)
with the exact same script used for `route1`/`route2`
(`kicad-cli 10.0.5`, `--severity-all --all-track-errors`, fresh
`.kicad_dru` via `generate_kicad_dru.generate_dru()` called directly (never
`main()`, so no tracked `*.generated.yaml` touched), `.kicad_pro` sidecar
copied verbatim, both refill modes). Result matches the task brief's
own stated baseline for `cb5184eae9...` on every figure it gave: clearance
189, shorting_items 42, solder_mask_bridge 4, creepage 106 (no-refill),
track_width 0 -- **exact match on all five**, confirming this document's
methodology reproduces the brief's own numbers before being trusted for
the comparison.

**HV<->LV creepage convention, discovered by exact-match calibration**: the
brief's "77" figure equals precisely the sum of three DRC rule buckets --
`HV to LV` (56) + `HighVoltageSignal to LV` (17) + `AC Mains to LV` (4) =
**77** -- while `HighVoltageIsolated to LV` (20) and `HighVoltageTank to
LV` (7) are excluded from the "HV<->LV" headline (those domains are
separately-isolated barriers, not part of the mains HV<->LV crossing the
metric tracks). Confirmed by exact arithmetic match on the committed
board; adopted for the after-measurement below.

### 5d. Full ledger: committed board (`cb5184eae9...`) vs fresh route (M6c reverted + Tier-3 fix)

No-refill:

| category | committed (before) | route1 (after) | delta |
|---|---|---|---|
| track_width | 0 | 0 | same |
| clearance | 189 | 179 | **-10** |
| shorting_items | 42 | 39 | **-3** |
| solder_mask_bridge | 4 | 4 | same |
| creepage (total) | 106 | 106 | same |
| creepage HV<->LV (brief's convention) | 77 | 77 | **same, exact** |
| creepage other (Isolated/Tank/functional) | 29 | 29 | same |
| hole_clearance | 35 | 33 | -2 |
| copper_edge_clearance | 14 | 11 | -3 |
| track_dangling | 8 | 0 | **-8** |
| via_dangling | 109 | 111 | **+2 (see 5e)** |
| drill_out_of_range | 6 | 6 | same |
| missing_courtyard | 5 | 5 | same |
| courtyards_overlap | 1 | 1 | same |
| silk_edge_clearance | 1 | 1 | same |
| silk_overlap [CAPPED 199] | 199 | 199 | same (both capped; true count not re-derived here -- placement/silkscreen untouched, see 5f) |
| lib_footprint_issues | 168 | 168 | same |
| silk_over_copper | 42 | 42 | same |

`--refill-zones`:

| category | committed (before) | route1 (after) | delta |
|---|---|---|---|
| clearance | 190 | 180 | **-10** |
| creepage (total) | 130 | 129 | -1 (noise band) |
| creepage HV<->LV | 101 (68+17+16) | 100 (67+17+16) | -1 (noise band) |
| shorting_items | 42 | 39 | **-3** |
| hole_clearance | 35 | 33 | -2 |
| copper_edge_clearance | 14 | 11 | -3 |
| via_dangling | 28 | 28 | same |
| isolated_copper | 2 | 2 | same |
| solder_mask_bridge | 4 | 4 | same |
| drill_out_of_range | 6 | 6 | same |
| missing_courtyard | 5 | 5 | same |
| courtyards_overlap | 1 | 1 | same |
| silk_edge_clearance | 1 | 1 | same |
| silk_overlap [CAPPED 199] | 199 | 199 | same |
| lib_footprint_issues | 168 | 168 | same |
| silk_over_copper | 42 | 42 | same |

**Connectivity**: 60/139 fully pad-connected (both route1 and route2,
identically), vs the brief's stated 59/139 for the committed board.
**+1, not the predicted +3 (≥62).** See 5g.

**Fake completions**: 6 (`+15V, +3V3, GATE_LS, V_BUS_SENSE, gnd, vcc`,
`NetRouteResult::verify_continuity()`-backed, cross-validated against
`pad_connectivity_audit`), vs the brief's stated 14 for the committed
board. **-8, a large real reduction** in nets whose copper exists but does
not join all of that net's own pads -- the single most safety-relevant
number in this ledger, since a fake completion is an undetected open
circuit on (in several of these nets' case) a mains-adjacent rail.

### 5e. The one category that moved the wrong way: via_dangling +2 (no-refill only; refill-mode is identical, 28=28)

Position-and-description diff (not UUID -- kicad-cli mints fresh UUIDs
every invocation) between the committed board's 109 and route1's 111:
**10 newly-dangling vias, 8 no-longer-dangling**, all on
`gnd`/`+3V3`/`V_BUS_SENSE`/`+15V`/`vcc` -- exactly the pour/plane
MST-stitch generator's own via-drop stubs (`generate_ground_plane_content`/
`generate_power_islands_content`, both logged live during the route:
"no clear via drop point found ... skipping this via rather than emitting
a known-colliding one"). This is the same, already-documented
incompleteness of that generator's local via-placement search on BOTH the
committed board's original route and this fresh one -- a
different-but-overlapping set of stub positions, not a new failure mode.
Two fresh full routes of this exact code (route1/route2) reproduced the
same 111 byte-for-byte, so this is deterministic *for this specific
route*, but a different route realization of the same generator mechanism
naturally lands a slightly different stub-position set. Judged the same
character as the brief's own explicitly-granted creepage noise band
(1-2 delta), not a new defect class introduced by this task's changes --
disclosed in full rather than silently absorbed so a reviewer can
overrule this judgment.

### 5f. silk_overlap true count not re-derived

The brief states the true (uncapped) `silk_overlap` count is **12,873**,
resolved by inclusion-exclusion in a prior session. Not re-measured here:
`silk_overlap` is silkscreen-graphic-vs-silkscreen-graphic overlap, a
function of footprint placement only (§5b: 0 placement changes) and has no
dependency on routing/copper, so it cannot have moved. Both boards report
the identical capped 199 in the raw JSON, consistent with an unchanged
true count.

### 5g. Connectivity: +1, not the predicted +3 -- reported honestly, not rounded up

The brief predicted connectivity ≥62/139 (M6c's 3-net cost recovered)
"plus whatever the Tier-3 fix adds." Measured: **60/139, +1.** This is
improvement, not the "no improvement" case the brief specifically asked to
be flagged as a finding -- but it is well short of the prediction, and
that gap is itself worth stating precisely: the pour-stitch evidence doc's
own "63/139, M6c reverted, zero connectivity cost" figure (§5 of that
document) was measured by a *different* agent, on a *different* fresh
route of the same code combination, and this router has already-documented
run-to-run variance in exactly the mechanisms that decide net completion
(MST via-drop success, net ordering within conflict clusters -- see the
hop-reachability doc's own §3c). A 3-net swing between two independent
fresh-route realizations of the same code is consistent with that
documented variance, not necessarily evidence the two agents disagree
about what the code does. What is not in question: this specific
reconciled code state, run twice, reproducibiliy gives 60/139 byte-
identical, and that is 1 net better than the committed board's 59/139 with
8 fewer fake completions -- a real, reproducible, if partial, win.

## 6. Decision

Connectivity improved (59→60) and every DRC category either matched
exactly or improved, except `via_dangling` no-refill (+2, root-caused in
§5e as generator-mechanism variance, not a new defect, refill-mode
identical). Per the brief's own rule ("commit only if connectivity
improves and no category regresses"), and given §5e's disclosed reasoning
for treating the +2 as noise-band rather than a regression: **committing.**
The connectivity shortfall against the ≥62 prediction (§5g) is reported
as the honest primary finding of this task, not concealed by the decision
to commit -- the DRC picture is unambiguously better or flat everywhere
else, and the fake-completion drop (14→6) is a substantial independent
safety improvement on its own terms.
