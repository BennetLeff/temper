---
module: pcb
tags: [placement, ampacity, ntc, drc, creepage, courtyard, power_in.ntc-no, discharge, ocp02, pd3]
problem_type: placement-fix
---

# 2026-08-16: Placement reconciliation — K1/RT1/U1/U2 cluster vs #1173's C7; T2/R65/C37 off-board staging; PD3 creepage hotspot ranking

## Scope and authority

Board edit authorized by owner for component placement. Scope: move only the
components that needed moving (K1, RT1, U1, U2, C7). All other components,
the board outline, and every DRC threshold/ceiling constant are untouched.
Worktree `fix/placement-reconciliation` off `origin/main @ fdbe0a6ad`, own
directory, never the main checkout. `pcb/temper.kicad_pcb` sha256
`077d4b69...f2fda` (main) -> `ddb96f9e...ef2` (this PR). No `git stash`,
no shared-venv writes: measurements used a private venv
(`/tmp/opencode/venv`) with `temper-design-bundle` (+ `temper-geometry`,
`temper-drc-rs`, `temper-io-types`) rebuilt from THIS branch's sources
(required: the installed shared-venv `.so` predates #1218/#1219, the
recovered IEC 60335-1 Table 16/17/18 `safety_value.rs` lookups the DRU
generator emits its safety constants from).

---

## Issue 1 — K1/RT1/U1/U2 cluster vs #1173's C7: DECISION = keep the cluster, move C7

### 1.1 The two PRs, and the actual conflict

**#1173 (merged, on main)** moved 8 components to resolve 7 of 8 tracked
`courtyards_overlap` pairs (`docs/evidence/2026-08-13-courtyard-collision-remediation-executed.md`).
Among them, **C7** (discharge snubber cap, `Capacitor_THT:C_Rect_L18.0mm_W11.0mm_P15.00mm_FKS3_FKP3`,
WIMA FKS3, 18x11mm, 15mm pitch; pads: `discharge.r_snub1-p2` net 44 + `PWR_RTN` net 13) was
moved **62.866mm from (137.72, 244.66) to (78.12, 224.66)** — the nearest courtyard-legal
spot found by #1173's free-space search, resolving the C5xC7 body interpenetration
(7.41mm overlap, the second-worst of the 8). The 8th pair, **C2xC3** (7.73mm body
interpenetration of two 35mm snap-in electrolytics — the worst), was deliberately NOT
touched by #1173; live DRC on current main confirms it remains the single
`courtyards_overlap` pair today (a `_march` claim that "#1176 closed C2xC3 on main" is
inaccurate: #1176's merge commit `5d165e84` is on the #1173 branch lineage, NOT an
ancestor of main — verified with `git merge-base --is-ancestor`).

**#1244 (open, `fix/ntc-replacement-v2`, base pre-#1173)** moves K1/RT1/U1/U2 into a
compact cluster in the bottom power pocket to shrink the `power_in.ntc-no` (net 88,
HighVoltage, 15A) pad span from 134.6mm to 26mm so a single 5mm pour hull can connect the
four pads (the documented 47-island zone-fill fragmentation at 140mm span —
`docs/evidence/2026-08-15-full-board-route-verification.md` — blocks net-level ampacity).

The conflict: **C7's new home (78.12, 224.66) sits inside #1244's cluster area.**
Verified with a shapely-based courtyard geometry check of the actual board file:
C7 at (78.12, 224.66) overlaps **K1, U1 and U2** at #1244's positions (K1 (90,222) r0,
RT1 (82,205.5) r0, U1 (60,218) r0, U2 (66,226) r180). The #1244 cluster itself is
courtyard-clear of every OTHER component on the current (post-#1173) board.

### 1.2 What was C7's original purpose/location, and could it have gone elsewhere?

C7's old spot (137.72, 244.66) collided with C5 (moved only 1.155mm by #1173, to
(139.62, 230.225)) — still overlapping C7's old position, so C7 cannot return there.
C7's courtyard-clear free space was re-searched from scratch on the CURRENT board
(post-#1173) with the cluster in place (shapely, 1mm grid, 0.05mm buffer margin,
boundary-correct polygon intersection — the first search pass using a hand-rolled
ray-casting point-in-poly was found to have the classic boundary-exclusion bug that
fabricated "legal" strips along other footprints' courtyard edges, and was discarded):

- **Bottom-right corner**: no room (C5, C8, R7, R14, C25, ex-U1 pocket too tight).
- **Mid-board (x 95-146, y 46-134)**: legal but inside the dense HV power section,
  100+mm from the discharge network, high new-violation risk.
- **Bottom pocket, between the cluster and C5**: a single thin legal strip at
  **x=112, y 216-222, rot 90** — 1.0mm courtyard gap to K1, ~25mm to R14 (its net-44
  partner), clear of C5's courtyard circle.

The strip was verified against every footprint with real polygon intersection
(shapely) and then **empirically confirmed by live kicad-cli DRC** on the edited board:
`courtyards_overlap` stays **1 (C2xC3)** — zero new overlaps, #1173's fix preserved.

### 1.3 Options evaluated

| Option | Result |
|---|---|
| **(a) Keep cluster, move C7 → (112, 218) r90** | **SELECTED.** Creepage 327-329 → **314** (deterministic across 15 + 120 samples, spread 1). Courtyards 1 (unchanged). Clearance TRUE 1105 → 1117 (+12, attributed). hole_clearance 96→90, shorting 197→189, solder_mask 147→139, pth_inside 1→0. Ampacity geometry achieved (24.4mm copper span). |
| (b) Manual 5.0mm ntc-no connection, no cluster | Rejected: requires a 140mm x 5mm copper swath through the densest region of the board — the exact geometry that fragmented into 47 pour islands; the pour's pinch points would become clearance violations on a fixed track. Strictly worse DRC cost; board also unrouted today. |
| (c) Different cluster location | Rejected: agent 53's exhaustive proof (14-15 new HV-LV creepage pairs over K1's 96 legal spots on the post-#1173 board) plus this session's corroborating geometry (the bottom pocket is the only region large enough for K1's 30.5x23.5mm courtyard; mid-board is blocked by C26/PS1). |
| Merge-order (land cluster first, #1173 re-chooses C7) | Moot: #1173 is already merged on main. Post-hoc equivalent of (a), which is what this PR implements. |

### 1.4 Measured DRC deltas (this PR's board, 120-sample protocol)

Protocol: `scripts/generate_kicad_dru.py` regenerated from this branch's SSOT,
`kicad-cli 10.0.5 pcb drc --all-track-errors`, single-thread `KICAD_CONFIG_HOME`
pin, scratch project dir (kicad_pro + fp-lib-table + libs + DRU) — the repo's
`ci_check_drc.py` protocol. Baseline (main, hash 077d4b69) re-measured first:
creepage 329 (record band {327:1, 328:12, 329:107}), courtyards 1 (C2xC3),
hole_clearance 96, shorting 197, solder_mask 147 — reproduces the committed record
exactly, validating the environment.

| category | main ceiling (077d4b69) | this PR (ddb96f9e) | delta | notes |
|---|---:|---:|---:|---|
| creepage | 331 (obs 327-329) | **315** (ceiling; obs 313-314) | **-16 ceiling / -13..-15 observed** | deterministic, spread 1; see 1.5 for attribution |
| clearance (TRUE, uncapped) | 1105 | **1117** | **+12 (RAISE)** | `measure_uncapped_drc.py dru-category clearance`, 2 independent runs byte-identical; attributed to relocation into a denser neighborhood (same class as #1244's own +21) |
| courtyards_overlap | 1 | 1 | 0 | same set (C2xC3), zero new |
| hole_clearance | 96 | 90 | -6 | |
| shorting_items | 197 | 189 | -8 | |
| solder_mask_bridge | 147 | 139 | -8 | |
| pth_inside_courtyard | 1 | 0 | -1 | |
| copper_edge_clearance | 7 | 7 | 0 | |
| drill_out_of_range | 4 | 4 | 0 | |
| hole_to_hole | 3 | 3 | 0 | |
| tracks_crossing | 1 | 1 | 0 | |
| track_width (TRUE) | 393 | 393 | 0 | no track edits |
| annular_width / via_diameter | 0 | 0 | 0 | |

Warnings: measured separately (default severity) — silk_over_copper 40 -> (measured on
edited board, see provenance), all other warning categories unchanged (see
`power_pcb_dataset/drc_ceiling.json` provenance for the per-category table).

### 1.5 Creepage attribution — what the cluster actually fixed, and what it cost

Per-violation item attribution of the baseline vs edited board creepage sets:

- **Fixed (-4 pad↔pad)**: `C8 x U1` (2 violations, 5.37/4.64mm) and `R6 x U2`
  (2 violations, 8.58/3.61mm) — U1/U2 leaving their scattered positions
  (168, 223.03)/(28.29, 175.44) removes them from C8's and R6's neighborhoods.
- **New (+2 pad↔pad)**: `C6 x U1` (2 violations, ~6.3mm) — U1 at (60, 218) sits above
  C6's `gnd` pad at (65.99, 211.76). **#1244's own "0 new HV-LV pairs" claim missed C6**:
  its verification checked the LV bottom row and R8/C1/R27 but not C6 (a 12.5mm disc
  Y-cap, `PWR_RTN` pad1 / `gnd` pad2, at (65.99, 201.76) rot 270). Attempted C6 moves
  were evaluated and rejected: C6 cannot simultaneously clear U1's two pads
  (>=12.6mm from (54.92,218) and (65.08,218)) and C1's pad (the pre-existing C1xC6 pair)
  without colliding with C1 or R26 (verified by search). Documented as follow-up, not
  silently absorbed.
- **Net -3 pad↔pad** (9 -> 6), plus a further ~-10/-12 from pad↔track and
  track↔track improvements around the vacated positions (total -13..-15 measured).

### 1.6 Ampacity geometry

`power_in.ntc-no` copper pads on the edited board: RT1.2 (89.50, 205.50),
U1.2 (65.08, 218.00), U2.1 (66.00, 226.00); K1.13 (86.83, 231.50) is an F.Fab-only
spade tab (external wiring, no copper). **Copper pad span 24.4mm x 26.0mm**
(was 134.6mm). A single 5mm pour hull can span the three copper pads; IPC-2221B
(k=0.048 external, 2oz, 40C rise) requires 4.16mm minimum for 15A — 5.0mm clears
with 1.8x margin at trace level (17.2A @ 20C / 23.3A @ 40C).

### 1.7 Files changed for Issue 1

- `pcb/temper.kicad_pcb`: exactly 5 `(at ...)` lines (K1, RT1, U1, U2, C7).
- `packages/temper-placer/configs/temper_constraints.references.yaml`: provenance
  hash re-point to the new board (same pattern #1244 used; see commit).
- `power_pcb_dataset/drc_ceiling.json`: provenance + `_march` + ceilings (below).

---

## Issue 2 — T2/R65/C37 off-board staging: placement is now feasible, but the part's intrinsic PD3 creepage defect still blocks fielding it

### 2.1 Current state

On the current board T2 (CST3015 current transformer, `safety.ocp2.ct`), C37
(`safety.ocp2.c_filter`, 0603) and R65 (`safety.ocp2.r_burden`, 1206) sit in the
resync tool's off-board staging row: T2 (100.0, 300.0), C37 (20.0, 272.12),
R65 (44.0, 272.12) — all outside the outline (x 20-172, y 20-254). T2's nets:
`hb-gnd` (net 55) + `DC_BUS_RTN` (5) primary; `s1` (105) + `gnd` (48) secondary
(per #1145, `hb-gnd` is HV, `s1`/`gnd` are SELV).

### 2.2 New finding: the prior courtyard-UNSAT no longer holds

The prior evidence (`docs/evidence/2026-08-13-ocp02-unplaced-subsystem-options.md`,
PR #1144) proved T2+C37+R65 courtyard-UNSAT against the pre-#1173 board (a3fbaff37)
— even a hypothetical part 16.6x smaller did not fit. **Re-verified against the
current board with the same shapely search: T2 alone now has 18 courtyard-legal
positions (2mm grid) at (132-136, 116-120), and joint T2+C37+R65 solutions exist**
(e.g. T2(132,116) r0, C37(92,130) r0, R65(94,132) r0). The #1173/#1134 board changes
freed this mid-right region (near K2/L2).

### 2.3 Why they are NOT placed anyway — the intrinsic defect is placement-independent

- **T2's CST3015 primary↔secondary separation is 9.1mm** (recomputed directly from
  the footprint's own pad table: primary pads 9x4.8mm at (±7.68, -6.85), secondary
  pads 3x4.6mm at (±6.88, 6.95); nearest edge-to-edge gap = 9.1mm) **vs the 12.6mm
  PD3 reinforced bar the DRU enforces** — matching PR #1146's measurement exactly.
  HV (`hb-gnd`, `DC_BUS_RTN`) to SELV (`s1`, `gnd`) at 9.1mm is a codified PD3
  violation **regardless of where T2 sits**.
- Prior ranked recommendation (`2026-08-13-ocp02-unplaced-subsystem-options.md` §8):
  **de-scope OCP-02** (Option 5, legitimate, bounded, not clause-mandated) until the
  CT isolation mechanism is re-engineered (Option 4, aperture/donut-primary CT for
  T1+T2 jointly). The slot-rescue study
  (`2026-08-13-hv-creepage-slot-rescue-t1-t2-u6.md`) rescues T1 and U6 with routed
  slots (T1: 15.53mm, U6: 14.85mm) but explicitly flags T2's slot as carrying an
  unverified structural/FEA question and a standard-interpretation open item, and
  T2 then had no placement — that placement now exists (2.2), so the slot question
  for T2 becomes live, but it is a separate scoped engineering task.

**Decision: keep T2/C37/R65 in staging.** Placing them would ADD a known, unfixable
9.1mm-vs-12.6mm PD3 violation to the board's measured state — the exact class this
project has repeatedly declined to ship (`2026-08-13-ocp02-unplaced-subsystem-options.md`
§8 "a redundant protection channel that is itself a codified creepage violation is a
liability sitting on the board, not a safety net"). Board enlargement is NOT needed
(the parts fit); the blocker is the CT isolation mechanism, which is an `elec/`
redesign, not a placement.

---

## Issue 3 — PD3 creepage hotspots: the "~485 from placement" premise is wrong; here is the real attribution

### 3.1 Measured total, current board

Live DRC on current main (077d4b69, regenerated PD3 DRU, `--all-track-errors`):
**329 creepage violations** (the committed band 327-329 — no "485" figure exists in
any current measurement; the largest documented PD3 total was 377 on an older board
hash in `docs/evidence/2026-08-15-pd2-pd3-data-driven-decision.md`). Attribution by
item type:

| class | count | fixable by placement? |
|---|---:|---|
| intra-footprint pad↔pad (isolator part limits) | 11 | **No** — part selection (K3 x4, K2 x4 relay coil↔contact at manufacturer's 10mm vs 12.6mm bar; C6 x1, U5 x1, R30 x1) |
| cross-component pad↔pad | 9 | **Yes** (all 9 are listed below) |
| pad↔track | 114 | Mostly routing (board is essentially unrouted) |
| track↔track / zone / other | 195 | Routing |

**Only 9 of 329 (2.7%) are placement-fixable pad↔pad pairs.** The bulk is routed-
copper debt on an unrouted board; the "485 hotspots from placement" framing does not
match the current board's measurements.

### 3.2 Cross-component pad↔pad pairs — the complete set, prioritized

| # | pair | actual (bar 12.6) | short by | fix | status |
|---|---|---:|---:|---|---|
| 1 | C8 x U1 | 5.37 / 4.64mm | 7.2-8.0mm | U1 moved to cluster | **DONE in this PR** (-2) |
| 2 | R6 x U2 | 8.58 / 3.61mm | 4.0-9.0mm | U2 moved to cluster | **DONE in this PR** (-2) |
| 3 | C1 x C6 | 12.51mm | 0.09mm | nudge C1 ~1mm N/W | next best move, ~1 violation |
| 4 | K3 x R60 | 12.17mm | 0.43mm | nudge R60 ~0.5mm | ~1 violation |
| 5 | J2 x PS1 | 12.31mm | 0.29mm | nudge J2/PS1 ~0.3mm | ~1 violation |
| 6 | C8 x R7 | 9.90mm | 2.7mm | nudge R7 or C8 | ~1 violation |
| 7 | L1 x R8 | 11.51mm | 1.1mm | **check netclass first** — `discharge.r_dis2a-p2` is classed LV-side vs `ac_n` mains; likely a classification question, not a move | verify before moving |
| — | C6 x U1 | ~6.3mm | 6.3mm | C6 move infeasible without new collisions (verified); part of cluster cost | follow-up |

Ordering rationale: smallest displacement per violation cleared. Items 3-5 are
0.1-0.5mm nudges; each clears 1 violation. Total pad↔pad exposure after this PR:
6 records (down from 9).

### 3.3 The other 318

- **11 intra-footprint**: relay coil↔contact (K2/K3, manufacturer 10mm rating vs
  12.6mm PD3 — part-selection; the repo's own K3 swap doc measured the achievable
  best-case 12.760mm with razor-thin +0.16mm margin and did not claim every pad pair
  clears), Y-cap (C6), and two SMD parts (U5, R30). Not placement.
- **114 pad↔track + 195 track↔track**: routing debt. The committed board is
  essentially unrouted (27/139 nets connected); these counts are expected to
  restructure when real routing lands. Top pad↔track components (C1 12, C27 10,
  C4 9, K2 9, C25 7, L1 6, U2 5, C6 5, C26 5, RT1 5) are the routing queue's
  input, not placement targets.

### 3.4 T1/T2/U6 exclusion

Consistent with the task and the cert-lab package
(`docs/evidence/2026-08-14-certification-lab-package-pd3-and-60664-4.md`), T1/T2/U6
pairs are excluded from the placement-fix list: T1/U6 carry intrinsic isolator
shortfalls (9.1mm/8.1mm) under review with the certification lab (plus the routed-
slot rescue path for T1/U6); T2 is Issue 2 above.

---

## DRC ceiling update (this PR)

- error_ceiling 2285 -> **2259** (clearance 1105->1117 +12; creepage 331->315 -16;
  hole_clearance 96->90 -6; shorting 197->189 -8; solder_mask 147->139 -8;
  all other error categories unchanged). Verified by
  `scripts/ci_check_drc.py --backend kicad-cli`: PASS (1446/2259 errors,
  355/13563 warnings within ceiling) and noise-headroom guard PASS
  (creepage ceiling 315 with observed spread 1: 315-314 = 1 >= 314-313 = 1).
- warning_ceiling 13562 -> **13563** (silk_over_copper 40->42 +2, the moved
  components' silk; pth_inside_courtyard 1->0 -1).
- `Ceiling-Approval:` trailer carried on the landing commit: the only rises are
  clearance +12 and silk_over_copper +2, genuine, attributed consequences of
  the relocation into a denser neighborhood (same class as #1244's own +21
  measurement; this PR's net is lower because C7's move keeps the cluster
  tighter). Measured-live: 120 samples, kicad-cli 10.0.5, clean tree,
  resolvable measured_at_commit (dcc96d099), input hash ddb96f9e matching the
  committed board; both the DRC-ceiling-approval gate and the
  measurement-provenance gate pass on this branch.

## Follow-ups filed (not done here, explicitly out of scope)

1. C6 x U1 (2 violations) — cluster's honest cost; C6 re-placement infeasible without
   colliding; needs C1/C6/R26 joint consideration.
2. C1/C6, K3/R60, J2/PS1, C8/R7 nudges (0.1-2.7mm) — each clears 1 pad↔pad violation.
3. L1/R8 — netclass classification of `discharge.r_dis2a-p2` before any move.
4. T2/C37/R65 — placement now feasible at (132-136, 116-120); fielding blocked by
   CST3015's 9.1mm-vs-12.6mm intrinsic PD3 gap; aperture-CT redesign (T1+T2 jointly)
   per prior recommendation, or a T2 slot study now that a location exists.
5. #1176's C2xC3 courtyard fix is NOT on main (branch-lineage only) — the `_march`
   claim that it landed "on main" is inaccurate; live DRC shows C2xC3 remains.
