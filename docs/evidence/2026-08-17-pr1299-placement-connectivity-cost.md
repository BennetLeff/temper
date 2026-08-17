<!-- provenance: commit=fa067a9523cba69978ea7216a65009f6343315a7 dirty=false (worktree agent-routing-completeness-recon, branched from origin/main at fa067a9523cba69978ea7216a65009f6343315a7. pcb/temper.kicad_pcb sha256 9c1f4a37b03c6433275704c3bed917f7ff16877c762f0aa8d37cc6858d7c16dd verified unchanged, never opened for writing -- both boards measured below are scratch copies: the committed board unmodified, and a `shutil`-style scratch copy with PR #1299's 5 component moves applied by .scratch/apply_pr1299_moves.py.) -->
---
title: "PR #1299's 5 placement moves: connectivity cost -- measured net +2, not a cost"
date: 2026-08-17
module: temper-placer
tags: [router, routing, placement, pad-connectivity, pr-1299]
problem_type: connectivity-cost-measurement
status: measured
---

# PR #1299's 5 placement moves — connectivity cost

**Why this measurement exists**: PR #1299 (`evidence/pd3-creepage-reexamination`)
proposes 5 component moves (C22, C1, C6, R51, U27) that clear 9/14 PD3
creepage violations, verified thoroughly for DRC (creepage 271→261,
uncapped clearance 1117→1114, no category regressed). **It never measured
routing connectivity.** Phase 1 of this task's own reconciliation
(`docs/evidence/2026-08-17-routing-completeness-reconciliation.md` §3)
found that the two prior placement passes on this board (#1269, #1279)
are plausible drivers of the 89→61 pad-connectivity drop, each moving
components specifically to clear creepage — the same shape of move
#1299 proposes. If that attribution is right, #1299's moves carry an
unmeasured connectivity cost the owner is not currently seeing before
deciding whether to authorize it.

**Board never modified**: `pcb/temper.kicad_pcb` sha256
`9c1f4a37b03c6433275704c3bed917f7ff16877c762f0aa8d37cc6858d7c16dd`,
verified unchanged before and after this measurement. Both routed boards
below are scratch outputs of `route_once()` (`scripts/route_board.py`),
one starting from the unmodified committed board, one starting from a
scratch copy with PR #1299's 5 moves applied
(`.scratch/apply_pr1299_moves.py`, which verified each component's
pre-move position against PR #1299's stated old coordinates before
writing the new ones — all 5 matched exactly).

## Moves applied (verbatim from PR #1299)

| ref | old (x, y, rot) | new (x, y, rot) | delta |
|---|---|---|---|
| C22 | (68.490, 189.100, 270°) | (68.490, 191.100, 270°) | +2.0mm Y |
| C1  | (51.490, 214.220, 90°)  | (52.490, 214.720, 90°)  | +1.0mm X, +0.5mm Y |
| C6  | (65.990, 201.760, 270°) | (66.990, 201.510, 270°) | +1.0mm X, −0.25mm Y |
| R51 | (33.230, 97.290, 90°)   | (34.730, 97.290, 90°)   | +1.5mm X |
| U27 | (34.100, 47.960, 90°)   | (33.100, 47.960, 90°)   | −1.0mm X |

## Method

Both boards routed with the identical recipe: `route_once()` (same code
path as `scripts/route_board.py`, default flags — no `--net-batching`,
the direct capacity-aware Stage 3 solver, the current recommended
recipe per Phase 1 §4), same `netclass_rules.yaml`, same worktree/tree
(`fa067a952`), same machine, run back-to-back. Connectivity measured by
the same `pad_connectivity_audit.audit_pcb_file()` used throughout this
task's Phase 1 reconciliation and every prior evidence doc in this
lineage.

## Result

Both routes wall-clock-comparable (baseline 327.8s; PR #1299-moved board
routed back-to-back on the same machine, same recipe).

| | baseline (committed positions) | PR #1299 (5 moves applied) | delta |
|---|---|---|---|
| fully pad-connected (audit) | 61/139 | **63/139** | **+2** |
| fake-completion | 8 | 7 | −1 |
| honest-gap | 70 | 69 | −1 |
| NetRouteResult: connected | 61 | 63 | +2 |
| NetRouteResult: partial | 8 | 7 | −1 |
| NetRouteResult: zone_dependent | 9 | 9 | 0 |
| NetRouteResult: failed | 61 | 60 | −1 |

**Net-level diff — 6 nets changed status, net +2**:

| net | baseline | PR #1299 board | direction |
|---|---|---|---|
| `WDT_KICK` | failed | connected | **gain** |
| `rtd_pan.r_low_top-inn` | failed | connected | **gain** |
| `safety.fault_any_or-y2` | failed | connected | **gain** |
| `sw` | partial | connected | **gain** |
| `discharge.q_dis_drv-g` | connected | failed | loss |
| `inb` | connected | failed | loss |

**PR #1299's specific 5 moves do NOT cost connectivity — they gain 2
nets net, with 4 nets improving and 2 regressing.** This is a real
measurement, not a "no effect" null result: 6 of 139 nets (4.3%) changed
status from a cumulative ≤2mm-per-component perturbation, so the moves
are **not connectivity-free either** — they reshuffle the A* search
space exactly as any placement change does, just with a favorable net
result here. Board sha256 reverified unchanged
(`9c1f4a37b03c6433275704c3bed917f7ff16877c762f0aa8d37cc6858d7c16dd`)
before and after both routes.

**Recommendation for the owner decision**: the routing-connectivity
objection to PR #1299 does not hold — applying these 5 moves is very
unlikely to make the board's routing worse, and on this measurement
makes it very slightly better, in addition to the already-verified DRC
gain (creepage 271→261, uncapped clearance 1117→1114, no category
regressed). The 2 regressed nets (`discharge.q_dis_drv-g`, `inb`) are
worth a human glance before merging (neither is safety-critical by name,
but this doc does not verify that), but they are not a reason to block
the PR on connectivity grounds — routing recovers 2 *other* nets in
exchange, on the same measurement.

## Does this confirm or refute Phase 1's placement attribution for 89→61?

**It complicates the attribution rather than confirming it cleanly.**
Phase 1 (`docs/evidence/2026-08-17-routing-completeness-reconciliation.md`
§3) named `#1269`/`#1279` (two 10-component placement passes) as a
plausible driver of part of the 89→61 drop, alongside `#1259`/`#1261`/
`#1267`'s obstacle-halo tightening. This measurement shows a **materially
smaller** placement perturbation (5 components, ≤2mm each) than either
of those passes, and it does **not** cost connectivity net — it gains
2. Two readings are both consistent with this result and neither is
ruled out:

1. **Placement moves cause churn proportional to their footprint**, and
   #1269/#1279's larger, more numerous moves (10 components each, with
   unknown per-component displacement — not measured in this task)
   simply churned more nets than this 5-move, ≤2mm set did, with the
   larger passes landing on the unlucky (net-negative) side of the same
   underlying reshuffling process this measurement shows for the small
   set (6/139 = 4.3% churn here; #1248's own placement move was measured
   at ~21/139 = 15% churn in the 2026-08-16 capstone doc, a comparable
   *rate* to this one scaled by a larger, unquantified footprint).
2. **The 89→61 drop is dominated by the obstacle-halo tightening
   (#1259/#1261/#1267), not placement**, and placement moves in general
   (at least at this magnitude) are closer to connectivity-neutral —
   this measurement's own net-positive result is some evidence for that
   reading.

**This measurement cannot fully distinguish the two** without also
routing the board at the exact `#1269`/`#1279` pre-move and post-move
positions (not attempted here — reconstructing those exact prior
positions from git history was out of this task's remaining scope).
What it DOES establish, cleanly: **placement moves reshuffle
connectivity by a few percent of nets regardless of direction**, and a
DRC-motivated move is not automatically a connectivity cost — the
opposite is equally possible and, in this one measured instance, is
what happened. Phase 1's §3 should be read as "placement changed
*something*, not necessarily costly by itself" rather than "placement
passes cost connectivity" — the stronger, better-evidenced part of that
section's causal case remains the three obstacle-halo-tightening commits
(#1259/#1261/#1267), each independently documented elsewhere (PR #1301,
the #1267 commit message, the capstone doc's OVP-zone-refusal finding)
to trade connectivity for correctness on its own, without needing a
placement confound at all.
