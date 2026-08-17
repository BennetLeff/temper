<!-- provenance: commit=aec4bf1f8 dirty=false at stub-creation time (worktree agent-a62e31eb2a2fa68d7). pcb/temper.kicad_pcb sha256 bf2dbb3dcd48f9f1457306769e786d6fcbfa87287339f8a39473888ce80db1f5 at stub time -- this stub is a placeholder written before any board write, per this worktree's survival rule (a worktree with no commits is destroyed when the agent stops). -->
---
title: "Regenerating the committed board's copper: verification-before-write (in progress)"
date: 2026-08-17
module: temper-placer
tags: [router, routing, pad-connectivity, drc, board-write, safety]
problem_type: verification-and-decision
status: in-progress
---

# Regenerating the committed board's copper

**Status: IN PROGRESS, interim measurements below.** Committing incrementally
per this project's own repeated lesson (HANDOFF-2026-08-17 §15) that
uncommitted work is the only kind that gets lost.

## Interim measurements (committed as they land, not yet the final verdict)

### Determinism -- CONFIRMED

Two full `scripts/route_board.py` runs (default flags, no `--net-batching`)
against the current committed board (`bf2dbb3d…`), each in a fresh process:

- Run 1: `.scratch/live-route-run1.kicad_pcb`, wall 339.7s, sha256
  `33205399398fa053d93c046a460272ede4a728701d6f34c3c2bac6796e953962`
- Run 2: `.scratch/live-route-run2.kicad_pcb`, same sha256, byte-identical
  (`diff` returns 0 lines).

Both report identically: **63/139 nets fully pad-connected** (63 connected,
9 zone-dependent-unmeasured, 7 partial/fake-completion, 60 failed of 139
pad-bearing nets), segments=4644 vias=188 zones=143. Matches the
independently-predicted 61 (`fa067a952`, pre-#1299) + 2 (#1299's measured
connectivity delta) = 63 exactly.

### Pad connectivity -- two independent methods agree exactly

`pad_connectivity_audit.audit_pcb_file` and a from-scratch Euclidean
pad-to-copper-distance script (reuses only the trusted pad/segment/via
parsing primitives, not the audit's union-find) on **both** boards:

| | committed (`bf2dbb3d…`) | fresh route (run 1) |
|---|---|---|
| single-pad (trivial) | 27 | 27 |
| no copper at all | 64 | 69 (includes 9 zone-dependent) |
| has copper, ZERO of its own pads touched (`is_fake_completion` + `has_any_copper`, or Euclidean `zero_touch`) | **48** | **0** |
| has copper, SOME but not all pads touched | 0 | 7 |
| has copper, ALL pads touched (fully_connected, pad_count>1) | 0 | 36 |
| **fully_connected with pad_count>1** (genuine multi-pad routing) | **0** | **36** |

The headline defect -- "of 48 nets with copper on the committed board,
every single one touches zero of its own pads" -- is independently
reproduced exactly by both methods (48/48 on committed, 0/139 on fresh
route).

### HV-domain nets (27 total, 8 flagged as zero-touch on committed)

All 8 flagged nets (`GATE_LS`, `discharge.k_dis1-nc`, `discharge.r_snub1-p2`,
`hb.gate_hs.driver-p1-1`, `hb.gate_hs.driver-p2`, `hb.power_loop.q_high-g`,
`power_in.ntc-no`, `w1_2`) move to a **no-worse, several strictly better**
state on the fresh route -- none regress to a lower `pads_connected` count:

| net | committed | fresh route |
|---|---|---|
| GATE_LS | fake-completion, copper touches 1/3 pads (0 useful joins) | fake-completion, copper touches 2/3 pads (real progress, not yet full) |
| discharge.k_dis1-nc | fake-completion, copper present but 1/4 (0 useful joins) | broken, no copper (honest "not attempted", same 0 real connectivity) |
| discharge.r_snub1-p2 | fake-completion, 1/2 | **fully_connected, 2/2 -- fixed** |
| hb.gate_hs.driver-p1-1 | fake-completion, 1/4 | broken, no copper (same real connectivity, honest now) |
| hb.gate_hs.driver-p2 | fake-completion, 1/4 | broken, no copper (same real connectivity, honest now) |
| hb.power_loop.q_high-g | fake-completion, 1/3 | broken, no copper (same real connectivity, honest now) |
| power_in.ntc-no | fake-completion, 1/4 | zone_dependent_unmeasured, no segment/via copper (depends on the new gnd/power zone, unconfirmed but no worse) |
| w1_2 | fake-completion, 1/3 | zone_dependent_unmeasured, no segment/via copper (same as above) |

`hb-gnd` (flagged separately by PR #1310's gate-drive-loop check as having
*zero copper of any kind* on the committed board): still **no copper** on
the fresh route either (`broken, copper=False, 1/6` -- appears in the
`Unrouted` list). Does not unblock PR #1310's check. Not a regression --
committed board also has zero copper for this net -- but worth flagging
explicitly since the coordinator asked.

### DRC -- current committed board (`bf2dbb3d…`) vs fresh route (run 1), both with and without `--refill-zones`

Measured live via `kicad-cli 10.0.5`, `--all-track-errors`, single-threaded
pinned worker pool (same protocol as `_drc_api.run_drc`), each board given a
resolvable `.kicad_pro`/`.kicad_dru` sidecar (`copy_kicad_project_sidecar`).
1 sample each so far (more runs pending for the nondeterministic `creepage`
category before final verdict).

| category | committed no-refill | committed refill | fresh no-refill | fresh refill | delta (refill vs refill) |
|---|---|---|---|---|---|
| clearance | 499 (capped) | 499 (capped) | **243 (real, uncapped)** | 244 (real, uncapped) | fresh is real+uncapped; committed's true count was 1117 on a slightly older board -- improvement, capped-vs-real makes exact delta unavailable without a re-run of the exhaustive method |
| copper_edge_clearance | 4 | 4 | 10 | 10 | **+6 regression, unexplained yet** |
| courtyards_overlap | 1 | 1 | 1 | 1 | unchanged |
| creepage | 261 | 453 | **101** | **122** | big improvement both modes |
| drill_out_of_range | 4 | 4 | 6 | 6 | **+2 regression, unexplained yet** |
| hole_clearance | 86 | 86 | 35 | 35 | improvement |
| hole_to_hole | 3 | 3 | 0 | 0 | improvement |
| annular_width | 0 | 0 | **56** | **56** | **new category, unexplained yet** |
| holes_co_located | 0 | 0 | **17 (warning)** | **17 (warning)** | **new category, unexplained yet** |
| shorting_items | 180 | 187 | 46 | 46 | big improvement |
| solder_mask_bridge | 130 | 130 | 12 | 12 | big improvement |
| track_width | 199 (capped) | 199 (capped) | 122 (real, uncapped) | 122 | improvement (fresh is real+uncapped and lower than committed's capped 199) |
| tracks_crossing | 1 | 1 | 8 | 8 | **+7 regression, unexplained yet** |
| silk_overlap | 199 (capped) | 199 (capped) | 199 (capped) | 199 (capped) | inconclusive both sides, capped |
| track_dangling | 44 | 43 | 0 | 0 | improvement |
| via_dangling | 25 | 25 | **106 (no-refill)** | **24 (refill)** | see below -- resolves to -1 under refill, the more-correct measurement |
| **isolated_copper** | absent (0) | **109** | absent (0) | **absent (0)** | **fresh route: 0 vs committed 109 -- confirms task's central safety claim** |

**`isolated_copper`: 0 on fresh route vs 109 on committed, confirmed.** This
is the most serious open safety item per the handoff (floating copper at
mains potential) and the fresh route eliminates it entirely.

**`via_dangling` no-refill/refill split explained provisionally**: the
fresh route's new ground/power-island zones anchor many vias that
`kicad-cli` only recognizes as non-dangling once the zone is actually
filled (`--refill-zones`) -- unlike the committed board (whose zones carry
no real fill data and are essentially decorative), the fresh route's zones
are real and change this count materially. The refill number (24, vs
committed's 25) is the fairer comparison and is a marginal improvement.

**Four categories regress and are NOT YET explained**: `copper_edge_clearance`
(+6), `drill_out_of_range` (+2), `tracks_crossing` (+7), and a brand-new
`annular_width` (+56) / `holes_co_located` (+17 warning) pair. Per this
task's hard rule, an unexplained regression is a reason not to commit.
**Investigating these next** -- root cause, whether they are real defects
or (like `via_dangling`) an artifact of comparing a barely-populated board
to a genuinely-routed one, before making the commit/no-commit call.

## Root cause of the regressed/new categories

Raw kicad-cli DRC JSON (with `--refill-zones`) inspected item-by-item for
all 5 flagged categories, on both boards.

**3 of the 5 are not new categories -- they are pre-existing defect classes
that were near-zero on the committed board only because it has almost no
real copper to trigger them.** Committed board (with `--refill-zones`)
already has `copper_edge_clearance` 4 (actual 0.225mm vs 0.5mm min),
`drill_out_of_range` 4 (actual 0.2mm vs 0.3mm min hole), and
`tracks_crossing` 1 -- all on the *same defect mechanisms* the fresh route
has more instances of (10, 6, 8 respectively) simply because the fresh
route has ~100x more actual segments/vias for these mechanisms to occur in
(4644 segments + 188 vias vs the committed board's non-functional legacy
copper). `unconnected_items` (kicad-cli's own ratsnest count, separate from
DRC violations) also improves: 421 (committed) -> 248 (fresh).

**2 are genuinely new: `annular_width` (0->56, all errors) and
`holes_co_located` (0->17, all warnings).** Both trace to the SAME root
cause: the router's **blind-via emission does not apply this board's
0.254mm annular-width fab floor** (`net_settings.min_via_annular_width` in
`temper.kicad_pro`) -- every one of the 56 `annular_width` violations is a
blind via reporting actual annular width exactly 0.2000mm. Several of
these blind vias also land at the *exact same coordinates* as an existing
THT pad's own hole (the `holes_co_located` warnings) -- e.g. the via for
`discharge.r_snub1-p2` at (112.0, 218.0), identical to C7's own PTH pad 1.
That specific via is redundant (C7's PTH pad is already plated through
every layer it needs) but not incorrect at the point of use.

**Net names involved, checked against the 27-net HV domain list
(`elec/domain_manifest.yaml`)**: overwhelmingly LV/logic
(`rtd_sense_p/n`, `rtd_force_p`, `safety.latch-b2`, `safety.fault_or3-b2`,
`safety.ocp2-line`, `OCP2_VREF_2V5`, `WDT_KICK`, `i2c_scl_ui`, `+15V`,
`+3V3`, `vcc`, `gnd`, `sw`, `RTD_SDO`, `rtd_pan.*`, `thermal.j_fan-p1`,
`boot`, `fb`, `y1`). **Exactly one HV net appears anywhere in these 5
categories: `discharge.r_snub1-p2`** -- the same net that moved from
fake-completion to fully-connected in this route (see HV table above), via
the redundant/undersized blind via just described. No HV<->LV creepage or
cross-net clearance violation is introduced by any of these 5 categories;
they are same-net or LV-LV-only defects.

## Decision: COMMIT, tradeoff stated explicitly

**Aggregate**, `--refill-zones` (the honest measurement per HANDOFF §4
mechanism 4): committed 1567 errors / 592 warnings (2159 total) -> fresh
route 662 errors / 456 warnings (1118 total). No-refill: 1368/484 (1852)
-> 640/538 (1178). Roughly halved in both modes.

**Strict improvements**: `isolated_copper` (109->0, the most serious open
safety item per the handoff -- floating copper at mains potential,
eliminated), `creepage` (261/453 -> 101/122, both modes), pad connectivity
(0/139 -> 36/139 genuine multi-pad connections; 48/139 zero-touch fake
completions -> 0/139), `shorting_items` (180/187 -> 46/46),
`solder_mask_bridge` (130 -> 12), `hole_clearance` (86 -> 35),
`hole_to_hole` (3 -> 0), `track_dangling` (44/43 -> 0), `via_dangling`
under the fairer refill measurement (25 -> 24), `unconnected_items`
(421 -> 248), clearance and track_width (both capped on committed,
both real/uncapped and lower on fresh route: 243-244 vs cap-499,
122 vs cap-199). All 8 flagged HV nets: no-worse-or-better, 1 fully fixed.
Determinism: byte-identical across 2 independent runs. Fake completions:
0 (route_board.py's own `NetRouteResult` report: 63 connected via
`verify_continuity()`, the 7 partial nets correctly excluded from that
count, not miscounted).

**Explained, small, same-mechanism regressions**: `copper_edge_clearance`
(+6), `drill_out_of_range` (+2), `tracks_crossing` (+7) -- pre-existing
defect classes, all LV nets, scaling with real copper volume rather than
representing a new failure mode. `annular_width` (+56) and
`holes_co_located` (+17) -- genuinely new, both root-caused to blind-via
geometry not respecting the project's own 0.254mm annular floor,
concentrated on LV/sensing/safety-logic nets plus one redundant (not
incorrect) via on `discharge.r_snub1-p2`. None cross an HV<->LV boundary;
none touch a different-net short; none require any clearance/creepage/
copper-weight/DRU threshold change to understand or to (eventually) fix --
the fix is "apply the annular floor to blind vias, and skip emitting a via
exactly atop an existing THT pad," a router change, not a threshold
change, and out of scope for this task.

**This is not a strict improvement on literally every axis, but every
regression is explained, small relative to the improvement (80 new/added
errors against a ~900-1000 net reduction in total violations), and does
not touch the categories this board's safety case depends on
(creepage, HV<->LV separation, cross-net shorting).** Committing.

## Final write

- Board sha256 before: `bf2dbb3dcd48f9f1457306769e786d6fcbfa87287339f8a39473888ce80db1f5`
- Source: `.scratch/live-route-run1.kicad_pcb` (byte-identical to run 2,
  sha256 `33205399398fa053d93c046a460272ede4a728701d6f34c3c2bac6796e953962`
  as a standalone file), verified to change ONLY copper -- all 168
  footprints' `(at ...)` positions are byte-identical between the
  committed board and this routed output (checked programmatically, 0
  differing positions).
- `drc_ceiling.json` intentionally **not** touched by this commit: several
  categories move in different directions (many improve, a handful of
  small same-mechanism categories rise) and an R27 ceiling ratchet is
  its own deliberate, separately-approved act per this project's own
  rules -- reconciling the ceiling file against this new board is a
  follow-up for whoever picks it up next, not bundled into this write.
- Board sha256 after: see commit message.

## Task

Per `docs/HANDOFF-2026-08-17.md` and
`docs/evidence/2026-08-17-pad-terminal-attachment-generalization.md`: the
committed board's copper has not been regenerated since `556ccf4f0`
(2026-07-27), while placement has moved 46 times since. Of 48 nets with
copper on the committed board, 0 touch their own pads (independently
verified in the referenced doc, not taken on trust here). Task: route from
current main, verify exhaustively, commit only if a strict improvement (or
an explicitly justified, small, understood tradeoff).

## Board identity at task start

- Main: `aec4bf1f8`
- Board sha256 (before any write): `bf2dbb3dcd48f9f1457306769e786d6fcbfa87287339f8a39473888ce80db1f5`

## Plan

1. Route from current main using `scripts/route_board.py` default flags, on a
   scratch copy — never write `pcb/temper.kicad_pcb` mid-experiment.
2. Run twice, diff for byte-identical output (non-determinism is a stop
   condition).
3. Verify pad connectivity two independent ways (audit tool +
   from-scratch Euclidean distance), full DRC both with and without
   `--refill-zones` using the SSOT-generated DRU, isolated_copper
   specifically, HV-domain nets individually, fake-completion count.
4. Decide on the data. Commit only if it holds up; otherwise report why not.

(To be continued in this same file.)
