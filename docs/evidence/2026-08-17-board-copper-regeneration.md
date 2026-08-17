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

## Not yet done

- Root-cause the 4 regressed/new categories above.
- Decide, on the full data, whether to commit.
- If committing: final sha256 before/after, full commit message with every
  measured number.

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
