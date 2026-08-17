<!-- provenance: commit=fa067a9523cba69978ea7216a65009f6343315a7 dirty=false (worktree agent-routing-completeness-recon, branched from origin/main at fa067a9523cba69978ea7216a65009f6343315a7. pcb/temper.kicad_pcb sha256 9c1f4a37b03c6433275704c3bed917f7ff16877c762f0aa8d37cc6858d7c16dd verified unchanged, never opened for writing -- both boards measured below are scratch copies: the committed board unmodified, and a `shutil`-style scratch copy with PR #1299's 5 component moves applied by .scratch/apply_pr1299_moves.py.) -->
---
title: "PR #1299's 5 placement moves: connectivity cost (DRC-only verification did not check this)"
date: 2026-08-17
module: temper-placer
tags: [router, routing, placement, pad-connectivity, pr-1299]
problem_type: connectivity-cost-measurement
status: in-progress
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

*(pending — baseline route in progress; PR #1299-moved board to follow)*

| | baseline (committed positions) | PR #1299 (5 moves applied) | delta |
|---|---|---|---|
| fully pad-connected (audit) | TBD | TBD | TBD |
| fake-completion | TBD | TBD | TBD |
| honest-gap | TBD | TBD | TBD |
| NetRouteResult connected | TBD | TBD | TBD |

## Is the 89→61 drop's placement attribution causal or merely correlated?

*(pending — this specific 5-move, DRC-motivated, small-scale (≤2mm)
perturbation is a much smaller and more controlled placement change than
#1269/#1279's 10-component moves each, so a large connectivity swing here
would be strong evidence that ANY DRC-motivated placement move on this
board carries a real routing cost, not just the two large historical
passes; a near-zero swing here would suggest the 89→61 attribution to
placement in Phase 1 needs to lean more heavily on #1259/#1261/#1267's
obstacle-halo tightening instead.)*
