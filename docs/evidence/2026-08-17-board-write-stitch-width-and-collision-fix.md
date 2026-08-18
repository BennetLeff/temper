<!-- provenance: commit=4d7373ecadfebfff79a74933c3ce441b6cc8e127 dirty=false (worktree agent-a77928be4db4676d4, main tip at task start, includes PR #1332). pcb/temper.kicad_pcb sha256 6ac8b1ca8a6400b7bd775f335c59fd0873b89b0ae4ce095be11a91f6395916e1 at stub time, matches task brief -- this stub is a placeholder written before any board write, per this project's survival rule (a worktree with no commits is destroyed when the agent stops). -->
---
title: "Applying PR #1329 + PR #1332 to the committed board — landing the stitch width and collision-check fixes"
date: 2026-08-17
module: temper-placer
tags: [router, zone-stitch, power-islands, drc, track_width, board-write]
problem_type: verification-and-decision
status: in-progress
---

# Applying PR #1329 + PR #1332 to the committed board

**Status: IN PROGRESS**, committed incrementally per project survival rule
(a worktree with no commits is destroyed on stop).

## Task

Both PR #1329 (stitch width 0.3mm -> 1.0mm derived from
`TEMPER_NET_CLASSES["Power"].trace_width`) and PR #1332 (collision-check
fix for the two previously-unchecked `_power_islands.py` emission paths --
`_blocked()`'s zero-width probe and the unchecked via-drop stub) are merged
to main (`4d7373eca`). **The committed `pcb/temper.kicad_pcb` still carries
120 `(width 0.3000)` traces and 120 corresponding `track_width` violations**
-- the artifact is stale relative to the code, per HANDOFF-2026-08-17 §12's
"validated on scratch copy, never applied to committed artifact" trap.

Two predecessor evidence docs establish the mechanism and measured effect:
- `docs/evidence/2026-08-17-stitch-width-fix-board-reroute.md` (branch
  `worktree-agent-a838d24359b83fcae`, width-fix-only, deliberately NOT
  merged/applied to the board -- measured `shorting_items` 53->130, +77,
  root-caused to an unchecked emission path, not "no room").
- `docs/evidence/2026-08-17-stitch-congestion-rootcause-and-fix.md` (PR
  #1332, merged as `4da46bac2`/landed as part of `4d7373eca` -- fixes the
  root cause, re-measures `shorting_items` 130->42, HV<->LV creepage 88->77,
  connectivity 59/139, determinism confirmed byte-identical across 2 runs).

Board identity at task start: main `4d7373ecadfebfff79a74933c3ce441b6cc8e127`,
board sha256 `6ac8b1ca8a6400b7bd775f335c59fd0873b89b0ae4ce095be11a91f6395916e1`
(unchanged from prior sessions; not touched by this task except with
explicit verification-first reporting per the owner's conditional
authorization).

## Plan

1. Isolated venv in this worktree (`make venv-isolate`/`uv sync`), verify
   `temper_placer.__file__` resolves inside this worktree, and
   `STITCH_TRACE_WIDTH_MM == 1.0` before trusting any number.
2. Route from current main (`4d7373eca`) on a scratch copy only, twice, for
   determinism.
3. Full DRC (`--severity-all --all-track-errors`, full project context,
   both refill modes) against the expected table in the task brief.
4. Independent connectivity check (both methods), fake completions, HV<->LV
   creepage breakdown, placement-invariance (0 footprint `(at ...)` lines
   changed), `grep -c "(width 0.3000)"` == 0.
5. Decide on the data against commit criteria. Write `pcb/temper.kicad_pcb`
   only at the final verified commit step.

(To be continued in this same file, appended incrementally as measurements
land.)

## Environment

Isolated venv provisioned in this worktree (`make venv-isolate`, required
`unset CONDA_PREFIX` first). Verified directly:
`temper_placer.__file__` resolves to
`.claude/worktrees/agent-a77928be4db4676d4/packages/temper-placer/...`
(inside this worktree, not the shared checkout), and
`temper_placer.router_v6._power_islands.STITCH_TRACE_WIDTH_MM == 1.0`.
`kicad-cli --version` = 10.0.5, matching the task brief.

Sibling routes observed running concurrently in a different worktree
(`agent-a117df333e1fd0c5f`) sharing this session's scratchpad path
prefix — not touched, own output directory used
(`.../scratchpad/a77928be4db4676d4/`) to avoid collision. `free -g` showed
23-25GB free throughout; no memory pressure.

## Route 1 + Route 2 (determinism)

`scripts/route_board.py` default flags, from this worktree's
`pcb/temper.kicad_pcb` (sha256 `6ac8b1ca...`, verified unchanged before,
between, and after both runs). Route1 wall 570.4s, route2 wall 534.3s.
Both: `59/139 nets fully pad-connected`, `fake-completion=14`,
`honest-gap=66`. Per-rail fallback drop counts identical both runs and
identical to PR #1332's own reported figures: `+3V3` 44 MST edges dropped,
`vcc` 12 edges + 2 stubs, `+15V` 8 edges, `V_BUS_SENSE` 3 edges + 1 stub.

**Output byte-identical**: route1 and route2 sha256 both
`cb5184eae9fea94c4b7b3c68c553ce97923a0d8f9af9d0fbb87442ab593c39b3` —
**this also matches PR #1332's own evidence doc's recorded route1/route2
hash exactly**, an independent cross-worktree reproduction of the same
deterministic route from the same board+code state.

## DRC — both refill modes, own kicad-cli invocation

`kicad-cli 10.0.5`, `--severity-all --all-track-errors`, full project
context (`.kicad_pro` + freshly-generated `.kicad_dru` + `fp-lib-table` +
`libs/` beside a scratch `.kicad_pcb` copy — never `pcb/temper.kicad_pcb`
itself).

| category | committed (no-refill/refill) | route1 = route2 (no-refill/refill) | expected (task brief) | verdict |
|---|---|---|---|---|
| **track_width** | 120 / 120 | **0 / 0** | 0 | **MET** |
| **shorting_items** | 53 / 53 | **42 / 42** | 42 | **MET** |
| clearance | 238 / 239 | **189 / 190** | 189 | **MET** |
| solder_mask_bridge | 15 / 15 | **4 / 4** | 4 | **MET** |
| hole_clearance | 26 / 26 | **35 / 35** | 35 | **MET** |
| creepage | 111 / 132 | **106 / 130** | 106 | **MET (no-refill); refill 130 vs task's implicit ~129 — within the documented ~0.8% creepage noise floor** |
| copper_edge_clearance | 12 / 12 | 14 / 14 | not in table | flat vs PR #1332's own reported 14/14; +2 vs committed, already analyzed there as a direct consequence of the width fix, not a new defect |
| track_dangling | 0 / 0 | 8 / 8 | not in table | matches PR #1332 exactly |
| via_dangling | 106 / 23 | 109 / 28 | not in table | matches PR #1332 exactly |
| isolated_copper | 0 / 1 | 0 / 2 | not in table | matches PR #1332 exactly |

`grep -c "(width 0.3000)"` on route1/route2: **0**.

**Every measured category reproduces PR #1332's own already-reviewed
ledger exactly**, both refill modes, own independent kicad-cli invocation
in a separate worktree — strong cross-validation, not a restatement of
trusted numbers.

## Mechanism verification for track_width = 0 (not "stitches stopped being emitted")

Per-net 1.0mm-width F.Cu segment counts on route1, own script parsing
`(segment ...)` blocks by net:

| net | 1.0mm-width segments | vias | verdict |
|---|---|---|---|
| `+3V3` | **89** | many | genuine 1.0mm backbone copper present |
| `+15V` | **32** | several | genuine 1.0mm backbone copper present |
| `vcc` | **0** | 11 | **zero stitch segments of ANY width** (not narrower fallback copper) |
| `V_BUS_SENSE` | **0** | 3 | **zero stitch segments of ANY width** |

**This needs stating plainly, not glossed over: `vcc` and `V_BUS_SENSE` do
not have "comparable coverage" to `+3V3`/`+15V` in this route** — their
entire MST backbone-edge sets (12 and 3 edges respectively, per the
router's own log) collided with foreign copper at the corrected 1.0mm
width and were dropped fail-closed by PR #1332's fix, leaving only via
drops with no interconnecting F.Cu stitch trace at all. This is not a
narrower-trace fallback (would itself be a `track_width` violation) and
not "stopped being emitted" as a design regression — it is the same
fail-closed behavior documented in PR #1332's own evidence doc, applied to
these two smaller/sparser rails to its logical conclusion (100% of their
edges collided, not merely some of them). `track_width` is genuinely 0
because no sub-1.0mm copper is emitted anywhere, on any of the four rails
— confirmed by the `grep -c` result above, not merely inferred from an
absence of segments.

## HV<->LV creepage — explicit breakdown, both refill modes, own methodology

Own script (`check_hv_netclass_coverage.load_hv_nets` against
`elec/domain_manifest.yaml`'s 27-net HV domain list — the project's own
canonical, machine-loaded source, not a hand-copied list), `[netname]`
extraction from kicad-cli JSON item descriptions, classifying each
creepage violation's exactly-2-net pair as HV<->LV / HV<->HV / LV<->LV:

| | committed no-refill | committed refill | route1 no-refill | route1 refill |
|---|---|---|---|---|
| creepage total | 111 | 132 | 106 | 130 |
| **HV<->LV** | **82** | 103 | **77** | 101 |
| HV<->HV | 29 | 29 | 29 | 29 |
| LV<->LV | 0 | 0 | 0 | 0 |

**Route1's HV<->LV figure (77 no-refill) matches PR #1332's own reported
figure exactly** — strong validation that this classification methodology
is consistent with the project's own later, more careful measurement.

**Disagreement to report, not reconcile**: the task brief's expected-table
"committed" HV<->LV baseline is **88** (inherited from the earlier,
unmerged width-fix-only evidence doc,
`docs/evidence/2026-08-17-stitch-width-fix-board-reroute.md`). My own
from-scratch re-measurement of the *same* committed board, same DRU, same
kicad-cli version, using the exact same classification method that
reproduces PR #1332's post-fix number exactly, gives **82**, not 88. I did
not chase this toward 88; multiple alternate groupings were tried
(unique-net-pair dedup: 107 total to-LV pairs; intra-vs-inter-component
split: 63 inter-component to-LV) and none reproduce 88 either, so this is
not a small parsing artifact resolvable by a different convention — it
looks like the 88 figure in the predecessor document itself does not
reproduce under independent re-measurement. **This does not change the
commit decision**: 77 is below both 82 and 88 in every refill mode, so
"HV<->LV creepage does not worsen" and "no worse than 88" both hold
regardless of which baseline number is correct. Flagged per the task's own
instruction to report disagreement rather than reconcile toward the
predicted number.

One classification-mismatch root cause found along the way: the net
`input` is declared HV-domain in `elec/domain_manifest.yaml`, but every
DRC violation involving it fires a `"... to LV"`-named rule (i.e. KiCad's
own enforced netclass/DRU treats `input` as LV) — a genuine, small,
pre-existing (not caused by this task) discrepancy between the aspirational
domain manifest and the enforced kicad_pro/DRU classification, orthogonal
to this task's scope and not touched.

## Connectivity — two independent methods

**Method 1** (`pad_connectivity_audit.audit_pcb_file`, the project's own
tested tool): committed board 63/139 fully_connected, 9 zone-dependent,
67 broken. Route1: **59/139** fully_connected, 9 zone-dependent, 71 broken.

**Method 2** (own from-scratch script,
`scripts/_agent_euclidean_connectivity.py`, layer-blind union-find over
independently-parsed pad/segment/via geometry — reuses the audit's tested
parsing helpers but implements its own graph-connectivity algorithm,
deliberately more permissive since it ignores per-layer isolation):
route1 gives **61/139**. The 2-net disagreement is `GATE_LS` and
`RTD_HW_FAULT` — **the exact same 2 nets the predecessor width-fix-only
evidence doc independently found and explained** (layer-blind
over-permissiveness, one-directional: Euclidean never calls a net broken
that the audit calls connected — confirmed here too, 0 audit-only
disagreements).

**4-net connectivity cost, confirmed exactly**: committed board's
63-connected set minus route1's 59-connected set = exactly 4 nets lost, 0
gained: `WDT_KICK`, `i2c_sda_ui`, `ina`, `rtd_pan.r_low_top-inn` — all
LV/logic, none HV, none Power-netclass, matching the handoff's own
documented mechanism (PR #1329's width correction via a Stage 3/4
corridor-mask side effect, not the collision-check fix). **The cost is
confirmed still 4 and still that mechanism** — not larger.

## Fake completions

**14**, both runs (route1 = route2, byte-identical output):
`+15V, +3V3, GATE_LS, I_SENSE, RTD_HW_FAULT, V_BUS_SENSE, bias, en, gnd,
ina, io0, safety.thermal.comp-inp, safety.uvlo_logic.mon-ina_p, vcc`. 0 of
these counted as connected in either the router's own log or the
independent `pad_connectivity_audit` cross-check (`NetRouteResult::Connected`
sourced only from `verify_continuity()`). Matches PR #1332's own reported
14 exactly, net-for-net.

## Placement invariance

Own script parsing every `(footprint ...)` block's `Reference` property
and `(at ...)` transform: **168/168 footprints identical between
committed board and route1**, 0 diffs.

## Full ledger vs. task brief's expected table

| category | committed | expected | measured | verdict |
|---|---|---|---|---|
| `track_width` | 120 | 0 | **0** | MET, mechanism verified genuine (not absent emission) |
| `shorting_items` | 53 | 42 | **42** | MET |
| `clearance` | 238 | 189 | **189** | MET |
| `solder_mask_bridge` | 15 | 4 | **4** | MET |
| `hole_clearance` | 26 | 35 | **35** | MET |
| `creepage` | 111 | 106 | **106** | MET |
| HV<->LV creepage crossings | 88 | 77 | **77** | MET; **baseline itself re-measured at 82, not 88 — disagreement reported above, does not affect verdict** |
| connectivity | 63/139 | 59/139 | **59/139** | MET, confirmed 2 independent methods, 4-net cost mechanism confirmed |
| fake completions | 14 | 14 | **14** | MET |

All HARD RULES respected: no clearance/creepage/copper-weight/DRU
threshold touched (only read via the generator); no check weakened;
`drc_ceiling.json` untouched; no oracle deleted/re-pinned; no
`pcb/temper.kicad_pcb` write until this final step; no `git stash` used.

## Commit decision

All criteria in the task's "Commit criteria" section are met:
`track_width` reaches 0 by the verified mechanism, no category regresses
beyond PR #1332's own already-reviewed full ledger (every measured number
matches it exactly), HV<->LV creepage improves in both refill modes under
both the inherited and the independently re-measured baseline, determinism
holds (byte-identical, cross-worktree-reproduced), and placement is
untouched (168/168 footprints identical). **Committing.**

`pcb/temper.kicad_pcb` sha256 before: `6ac8b1ca8a6400b7bd775f335c59fd0873b89b0ae4ce095be11a91f6395916e1`.
`pcb/temper.kicad_pcb` sha256 after: `cb5184eae9fea94c4b7b3c68c553ce97923a0d8f9af9d0fbb87442ab593c39b3`
(the byte-identical route1/route2 output, written only at this final step;
never touched mid-experiment). No footprint `(at ...)` line changed (168/168
identical) — this is purely a routing/copper write, not a placement change.
