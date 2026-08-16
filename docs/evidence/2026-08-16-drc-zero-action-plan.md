---
module: pcb
tags: [drc, routing, action-plan, path-to-zero, creepage, clearance, zone-fill, placement]
problem_type: plan
date: 2026-08-16
---

# DRC-zero action plan — the definitive path to a fabricable board (2026-08-16)

**Scope**: integrates every 2026-08-15 session finding — agent 59's DRC
violation classification, agent 57's unrouted-nets root cause (M1–M5),
agent 58's router-honesty audit (via-type), agent 64's Rust zone-pour
design, agent 62's pad-avoidance fix (width-agnostic C-space), agent 69's
capstone route verification, the Stage 3 SAT memory investigation (agent 4),
and the net-filter/width-passthrough fix (agent 13, #1222) — plus the
2026-08-16 Stage 3 auto-batch default fix (this branch).

**Headline**: the router-side root causes of the 2026-08-15 routed-board
DRC count are now **fixed on main** (#1245, #1246, #1222, #1220, #1223,
#1221, #1200). The remaining path to zero is dominated by (1) the
width-aware C-space router fix (in progress by another agent), (2) a zone
redesign with a real fill pass, (3) placement-domain creepage work, and
(4) three owner decisions (T1/T2/U6 cert-lab creepage credit, the
C2/C3 placement, Power-class coil-net reclass). **No number in this plan
was re-measured after #1245/#1246 landed** — the first action in the
dependency graph is that re-measurement, on the output of the auto-batch
route this branch enabled.

---

## 1. Current state

### 1.1 Fixed on main (origin/main @ fdbe0a6ad, 2026-08-16)

| # | Fix | PR/commit | What it closes (from the 08-15 findings) |
|---|---|---|---|
| 1 | Stage 3 selective-SAT net filter wired for real (`max_sat_nets` → `ModelBuilder(net_filter=...)`) | #1222 | The print-only `_select_sat_nets` defect (memory investigation §5.4). |
| 2 | Stage 4.4 trace-width pass-through (`design_rules` threaded into `assign_trace_widths`) | #1222 | Declared netclass width reaching drawn copper (memory investigation §7.1: `power_in.ntc-no` was 0.508 mm vs declared 5.0). **FinePitch 0.127 → 0.2 resolved.** |
| 3 | **Stage 3 auto-batch default** — `--net-batching` defaults True; monolithic Stage 3 auto-routes through batching when the raw model exceeds 2.5M vars | **this branch** | The 182–200 GB monolith OOM (110 nets × 204K edges = ~22.5M vars; measured again here at **35.4M** on the 6-layer board). The default `route_board.py` invocation (no flags) can now complete. |
| 4 | PD3 creepage enforcement (12.6 mm reinforced / 10.0 mm tank), Gate 4 blocking | #1220/#1229 | The PD2-vs-PD3 decision executed: PD3 governs the as-built board. |
| 5 | IPC-2221B width correction (k=0.048/0.024, copper-oz, material group) | #1223 | Authoritative ampacity kernel (`temper_drc_rs::ipc`). |
| 6 | Parser retains single-pad nets | #1221 | 139-net registry; `ac_l`/`ac_n` classification correct. |
| 7 | **Rotation-aware zone pad positions** (`run_collect_pad_positions` through `pin_world_position_at_py`) | #1245 | M2 (9 zone nets, hulls around wrong coordinates) **and** the 14 pad-swap stitch shorts (`w1_1`↔`ac_n`, `w1_2`↔`ntc-no`, ...) that produced the 204 `shorting_items` / 2 `tracks_crossing` class. Structurally impossible after this. |
| 8 | **Via-type emission** (`blind`/`buried`/`micro`/through tokens) + audit reads the type token | #1245 | Agent 58's via finding: every via was a phantom through via. -6 provable phantom shorts, -22 phantom hole-clearance, +6 revealed dangling vias. Audit and KiCad now agree. |
| 9 | **`enable_all_pad_tree` default True** (multi-pad waypoint expansion) | #1245 | M3: 22 nets that routed only 2-of-N pads (A* capable, pads not in waypoint list). |
| 10 | **gnd In1.Cu ground plane wired into production** (`generate_ground_plane_blocks` from `_adapter_convert._write_routes_to_content`) | #1245 | `gnd` (88 pads) had **no copper mechanism at all** — no zone, plane generator caller-less. Now emits a real plane. |
| 11 | Pad-connectivity audit 3 metric defects (union-find stale root, `_cluster_key` tie, zone blindness) | #1200 | The "52/87" vs "59/139" under-reporting class. |
| 12 | Occupancy-grid containment rasterized in Rust | #1245 | 47.5 s → 0.38 s per route (perf; unblocks re-measurement cadence). |
| 13 | 7 of 8 courtyard-collision pairs landed | #1173 | `courtyards_overlap` 8 → 1 (remaining pair C5×C7; C2×C3 deliberately deferred, safety-unchecked). |
| 14 | **Pad-layer landing** (`_land_route_on_pad_layers`, extracted from #1196/#1197) | #1246 | M1: 32 nets landing at pad coordinates on the wrong layer with zero vias. |
| 15 | ZCD removal resync, designator renumber | #1201/#1134 | Board content aligned with schematic. |
| 16 | Functional-insulation tier + PD2→PD3 retarget complete | #1237/#1238 | 6.0 mm PD2-era sites updated to 12.6 mm (strengthening direction). |

### 1.2 In PRs / in progress (not on main)

| Item | Status | Owner/PR |
|---|---|---|
| **Width/clearance-aware C-space** (the residual ~184 shorts: occupancy grid marks every path at `default_trace_width_mm=0.2` while emitted widths reach 5.0 mm; static-obstacle halo is width-agnostic) | **being fixed by another agent** (agent 62's follow-up #1) | per-net marking width+clearance at route time + per-net static halo |
| Rust zone-pour generator (`pour_outline` + KiCad hole-format emitter) | designed, prototyped, 8/8 Rust tests, kicad-cli-verified — **wire-up into `_emit_zone_pours` is the next step** | `feat/rust-zone-pour-design` (agent 64) |
| Creepage carve table (`zone_pour_creepage.generated.yaml` twin of the clearance table) | needed by the zone wire-up | — |
| T2 / OCP-02 subsystem placement (CST3015 CT, R65, C37) | `repair-unplaced` entry point landed (#1144); actual placement outstanding | — |
| K1 replacement part (PD3 gap) | staged in PR #1156 | — |
| Drift gate `[clearance/reinforced]` 2.0 vs 6.0 mm | owner decision (a/b/c in pending-decisions doc) | — |
| PR #1178 stack remnants | #1246 extracted the routing half onto main; verify nothing else blocks | — |

### 1.3 Outstanding (measured, not yet acted on)

- **No zone-fill pass anywhere** — 0/231 `filled_polygon` blocks on the routed board; every zone-dependent net is "cannot measure" until fill runs.
- **Creepage on a routed board at PD3: 511** (485 outside T1/T2/U6) — the dominant category, placement-domain.
- **T2 (OCP-02 CT) off-board / unplaced** in the classification's board; 5 unconnected items trace to it (the root-cause doc's board has it present — board versions differ; either way the subsystem is not placed on the production board).
- **Power-class coil nets at 0.2 mm** (k_dis1-coil1/2, k_dis2-coil1, 199 track_width items, saturated) vs the 1.0 mm Power minimum.
- **C2×C3**: 199 silk_overlap + 7.73 mm courtyard overlap — deliberately untouched (safety-unchecked placement of the two big THT caps).

---

## 2. Remaining DRC violations after all identified fixes land — estimate

Base: agent 59's routed 6-layer board classification (pre-#1245/#1246),
2248 errors + 519 warnings unfilled, 329 unconnected items, measured with
the PD3 DRU (12.6 mm reinforced). Landed fixes subtracted per their own
measured deltas. **This is an estimate, not a measurement** — the
first post-fix route (this branch's auto-batch output) is the re-anchor.

| Category | Classified | Landed since | Residual after landed | Fix that zeroes it | Status |
|---|---:|---:|---:|---|---|
| shorting_items | 204 | −14 pad-swap (#1245) −6 phantom via (#1245) | **~184** | width-aware C-space (per-net width+clearance marking) | in progress |
| tracks_crossing | 2 | −1 swap | **~1** | same C-space fix | in progress |
| creepage | 511 | — | **511** (431 routing + 41 placement + 21 same-footprint + 18 T1/T2/U6) | live HV↔LV creepage in router + placement + cert-lab | hard |
| clearance | 499 ⚠ sat | — | **~499** | live clearance gate (0.2–2.0 mm by rule) | moderate |
| unconnected_items | 329 | M1/M2/M3 connectivity | **~54–90** | zone fill + T2 placement + residual M4 | hard |
| track_width | 199 ⚠ sat | FinePitch fixed (#1222) | **199** (all Power-class coil nets) | route at 1.0 mm or reclass to FinePitch | trivial–moderate |
| solder_mask_bridge | 208 | −~22 phantom via | **~186** | same clearance-gate work (pad-proximity) | moderate |
| hole_clearance | 199 ⚠ sat | −22 phantom via | **~177** | via/hole rules live in router | moderate |
| silk_overlap | 199 | — | **199** (all C2/C3) | C2/C3 placement (owner decision) | trivial* |
| silk_over_copper | 61 | — | 61 | footprint silk edit (refs off pads) | trivial |
| copper_edge_clearance | 44 | — | 44 | 0.5 mm edge keepout live in router | trivial |
| track_dangling | 34 | +6 revealed by via-type fix | **~40** | route cleanup / stub removal | trivial |
| holes_co_located | 14 | — | 14 | no via-in-PTH-pad rule | trivial |
| courtyards_overlap | 8 | −7 (#1173) | **1** (C5×C7) | place C5/C7 apart | trivial |
| via sizes (dia/drill/annular) | 18 | — | 18 (RTD_SDO) | via sizing ≥0.5/0.3/0.15 | trivial |
| via_dangling | 2 | +6 revealed | ~8 | finish/remove | trivial |
| lib_footprint_mismatch | 26 | — | 26 | library sync | trivial |
| lib_footprint_issues | 13 | — | 13 | fp-lib-table / library presence | trivial |
| missing_courtyard | 5 | — | 5 | add courtyards to 5 footprints | trivial |
| silk_edge_clearance | 1 | — | 1 | move TP4 silk | trivial |
| pth_inside_courtyard | 1 | — | 1 | move C7/C5 | trivial |

**Estimate after all router fixes land (before placement/zone/owner work):
roughly 1800–2100 of the original 2248 routed-board errors are addressed
by the router fixes above; the rest (~1500 remaining before the final
placement/zone/owner pass) decompose as**:

- **~184 shorts** (width C-space, in progress) — fab-blocking, non-negotiable.
- **~499 clearance + ~186 mask + ~177 hole + ~44 edge** ≈ **~900** — the
  "live constraints" cluster; one coherent router change (constraints in
  the occupancy/A* model), not nine.
- **~511 creepage** — the defining safety constraint; placement-domain
  majority (see §3).
- **~199 track_width** — config-or-routing, trivial.
- **~54–90 unconnected** — zone fill + T2 placement.
- **~350 silk/library/trivial** — mechanical.

**The honest bottom line (unchanged from agent 59, now sharper)**: DRC-zero
is achievable, but not by re-routing alone. The two hard prerequisites are
the width-aware C-space fix (dead shorts) and the zone redesign + fill
(gnd/+3V3/zone nets connect **and** stop creating +222 fill-creepage).
After those, the count is dominated by a constraint-respecting re-route
plus placement moves, with the T1/T2/U6 cert question the only items that
need an owner rather than an agent.

---

## 3. Per-category remaining items and fix path

### 3.1 Shorting / crossing — width-aware C-space (+ residual)

- **Classified**: 204 `shorting_items` + 2 `tracks_crossing`. Decomposed by
  agent 62: **14 pad-swap stitches** (rotation-omission — **fixed, #1245**,
  structurally impossible now) and **~190 width-mismatch overlaps** (the
  real residual): the occupancy grid marks every routed path at
  `default_trace_width_mm = 0.2` and halos static obstacles at
  `default_trace_width_mm / 2 = 0.1`, while emitted widths are per-netclass
  up to **5.0 mm** (HighVoltage). A 0.2 mm model lets later nets cross
  earlier 5.0 mm trunks and lets 0.5 mm tracks pass ~0.2 mm from pads —
  actual geometric overlaps.
- **Fix (in progress, another agent)**: per-net width- and clearance-aware
  C-space at route time — mark each routed path with the net's own
  width+clearance; give static obstacles a per-net halo. Agent 62's note
  stands: a global raised halo is unsound (5 mm + 2–6 mm HV clearance would
  block the whole board). The netclass widths are available at route time
  and already match emitted widths — the track-marking half is small; the
  static-halo half is the architecturally significant piece.
- **Residual after that**: ~0. The 1 residual `tracks_crossing`
  (`safety.ovp.r_adc_top1-p2` × `power_in.ntc-no`, width-mismatch class)
  dies with the same fix.
- **Gate**: fab-blocking — no board with dead shorts is fabricable,
  regardless of every other category.

### 3.2 Creepage — placement moves + T1/T2/U6 cert-lab (owner)

- **Classified (routed board, PD3 12.6 mm)**: 511. Breakdown: **431 routing**
  (pad-track 381, track-track 31, pad-via 28, track-via 9), **41 placement**
  (pad-pad, different components), **21 config same-footprint** (7 of them
  T1/T2/U6 pad-pad = cert-lab question), **18 routing T1/T2/U6-involved**.
  Component top: U24 32, RT1 23, K2 22, U6 21, U27 21, L1 17, K3 16,
  U14 15. **485 of 510 do not involve T1/T2/U6** (agent 69).
- **Committed-board context** (pd2/pd3 decision doc): PD2 = 199 (passes the
  202 ceiling with 2–3 headroom); PD3 = 377–379 committed (would exceed by
  ~175). The routed board pays the routing win's cost: +132 over committed
  at PD3.
- **Fix path**:
  1. **Router live HV↔LV creepage** (the 431 routing items): the router has
     a creepage-aware clearance gate (`router_clearance.rs`, PR #1198
     material) — it must be live for these pairs. 12.6 mm PD3 is the
     board's defining constraint; a legal-path search that fails honestly
     is the expected outcome for some pairs (i.e. some nets genuinely
     cannot route at PD3 with the current placement — see dependency graph).
  2. **Placement moves** (41 pad-pad + the top-component list): re-place
     U24/RT1/K2/U6/U27/L1/K3/U14-adjacent parts. The 08-15 classification
     and the K1-replacement PR (#1156) both show ~half the count is
     isolator-adjacent and partly owner-domain.
  3. **Same-footprint config (21)**: rule precision — same-footprint
     pad-pad creepage needs the DRU's same-footprint exemption semantics;
     the 7 T1/T2/U6 of these are the cert-lab question.
  4. **T1/T2/U6 cert-lab (7–18 items)**: PD3 island-slot creepage credit
     for the isolation barrier — **owner decision, not a re-route**.
     Package already drafted (`cert-lab-package` branch; two questions:
     island-slot credit, IEC 60664-4 applicability at 44–50 kHz).
  5. **K1**: verified replacement part staged in PR #1156 (PD3 gap).
- **PD3 vs PD2 note for the plan**: PD3 (12.6 mm) is decided and enforced
  (#1220/#1229). Do not re-litigate; the PD2 figure must not reappear
  (the drift gate fails closed on it).

### 3.3 Clearance — live constraints in the router

- **Classified**: 499 (saturated cap → lower bound). All items are
  track/via vs track/pad: 187 Default routing, 143 HighVoltageSignal→LV,
  105 HV→LV, 31 HVIsolated same side, 15 HVTank→LV, 9 netclass, 9 AC→LV.
- **Fix**: the router respects clearance (0.2–2.0 mm by rule) — most items
  are tracks routed too close to pads/tracks because the occupancy grid's
  halo is the 0.2 mm default, not the per-net figure. **Same root as the
  width C-space fix** (3.1): per-net clearance halos fix clearance + mask +
  hole + edge in one coherent change. The live clearance gate
  (`router_clearance.rs` material, PR #1198) is the enforcement seam.
- **Measured sanity check**: committed-board clearance is 1105 (ceiling,
  120 samples) — the routed board's 499 saturated count is *lower* than the
  committed board because the router writes less copper, not because it is
  cleaner. Both need the same fix.

### 3.4 Unconnected — zone fill + missing component placement

- **Classified**: 329 (272 pure-routing, 57 zone-covered nets, 5 OCP-02/T2).
  Zone-fill test: **fill resolves only 3 of 57** zone-net items and *adds*
  +222 creepage + 167 isolated_copper islands — the "fill will fix it"
  hypothesis fails because the zone *outlines* are wrong (M2: rotation-blind
  pad coordinates → hulls around wrong positions; **fixed in #1245**) and
  fragment (single-hull over dense board, holes dropped from outlines).
- **Fix path**:
  1. **M1/M2/M3 connectivity fixes land** (all on main now: #1246, #1245):
     the 272 pure-routing items are mostly wrong-layer landings, 2-of-N
     pads, and no-path nets. Agent 57's M-table: 32 M1 + 9 M2 + 22 M3 +
     11 M4. With the fixes in, the honest-gap list should collapse — the
     re-measurement (dependency graph step 1) is what confirms it.
  2. **gnd / +3V3**: gnd's In1.Cu plane is now wired (#1245); +3V3 stays
     Power/trace-only per the R1/R7 policy — at 50 pads the A* trace route
     is not viable, so +3V3 needs a per-net pour decision (agent 64
     measured: only 19/50 +3V3 pads can be pour-covered at PD3 anyway; the
     rest are A* burden).
  3. **Zone redesign + fill** (agent 64's Rust `pour_outline`):
     holes preserved, pair-creepage carve (12.6/10.0 mm halos, not the
     2.0 mm clearance carve), honest island policy, then a real fill pass
     (`kicad-cli pcb fill-zones` or faithful reimplementation). The audit's
     `zone_dependent_unmeasured` becomes measurable only after fill exists.
     **`power_in.ntc-no` at PD3 is infeasible as a single hull on any
     layer** (0/4 pads covered even with the new algorithm) — needs
     re-placement of K1/RT1/U1/U2 or manual 5.0 mm routing.
  4. **T2 / OCP-02 placement** (5 items): place the CST3015 CT on-board
     (`repair-unplaced` landed, #1144); re-verify R65/C37.
- **Note**: unconnected is measured at pad-pair granularity by DRC and
  net-level by the audit — the two reconcile (agent 58); don't double-count.

### 3.5 Track width — FinePitch fixed, Power-class coil nets

- **Classified**: 199 (saturated). All: Power rule min 1.0 mm, actual
  0.2 mm, on `discharge.k_dis1-coil1` (104), `k_dis2-coil1` (53),
  `k_dis1-coil2` (42) — relay coil-drive nets.
- **Fix**: **FinePitch 0.127 → 0.2 is fixed** (width passthrough, #1222).
  The remaining 199 are the three coil nets, classed Power in `.kicad_pro`
  but routed at 0.2. Two paths: route them at 1.0 mm, **or reclass to
  FinePitch** (relay coils; 0.2 mm may be electrically adequate — a
  legitimate config alternative, unlike the manufacturing-rule escape
  hatches the handoff forbids). Owner call on reclass; the routing half is
  the same constraint-respecting re-route as §3.3.

### 3.6 Silk / courtyard — placement

- **Classified**: silk_overlap 199 (all C2/C3 — the two big THT caps),
  silk_over_copper 61 (ref-fields over copper), courtyards_overlap 8→1
  (C5×C7; C2×C3 deferred), silk_edge_clearance 1, pth_inside_courtyard 1.
- **Fix**: mechanical placement/silk edits. **C2×C3 is the only
  decision**: moving the two big caps is safety-unchecked work (agent
  #1173's commit explicitly defers it) — 199 silk + 1 courtyard items wait
  on that owner decision. Everything else is trivial footprint/silk
  cleanup.

### 3.7 Mechanical/config — library sync

- lib_footprint_mismatch 26, lib_footprint_issues 13, missing_courtyard 5,
  track_dangling ~40, via_dangling ~8, holes_co_located 14, via sizes 18,
  copper_edge 44. All trivial; bundled with the constraint-respecting
  re-route (edge keepout, via rules) plus one library-sync pass.

---

## 4. Dependency graph — what must land before what can be measured

```
Step 0 (DONE, this branch): Stage 3 default no longer OOMs
        → the no-flags route completes → the measurement loop is unblocked
        └─ everything below depends on being able to route at all

Step 1 (FIRST ACTION): re-route on current main + re-measure
        route_board.py (no flags) → DRC + fixed audit + honesty verifier
        Dependency: Step 0. Every number in this plan is pre-#1245/#1246;
        the post-fix route is the new anchor for all estimates below.
        Also re-measure the committed board (drc_ceiling.json duty: any
        pcb/temper.kicad_pcb touch re-measures in the same PR).

Step 2: width-aware C-space router fix (in progress, another agent)
        Unblocks: shorting ~184 → 0; and with per-net clearance halos,
        the clearance 499 / mask ~186 / hole ~177 / edge 44 cluster.
        Dependency: none (independent of zones/placement).
        NOTE: creepage 12.6 mm must be INCLUDED in the per-net halo set
        for HV↔LV pairs, or the 431 routing-creepage items persist.

Step 3: zone redesign wire-up (agent 64's pour_outline into _emit_zone_pours)
        + creepage carve table + real fill pass (M2b)
        Unblocks: zone-net unconnected (54), gnd plane correctness,
        and STOPS the +222 fill-creepage / 167-island regression.
        Dependency: Step 2's per-net halos reduce the obstacle set the
        pour must carve around (a pour carved against phantom 0.2 mm
        copper is wrong); can proceed in parallel but its *measurement*
        (fill + DRC) is only meaningful after Step 2.

Step 4: placement passes
        4a. T2/OCP-02 on-board (unblocks 5 unconnected + enables OCP2 nets)
        4b. creepage placement moves (41 + top-component list U24/RT1/K2/
            U6/U27/L1/K3/U14-adjacent)
        4c. C5×C7 + C2×C3 (the latter is an owner decision)
        Dependency: 4b/4c must land BEFORE the final re-route (moving
        components invalidates routed copper). 4a is independent.

Step 5: live HV↔LV creepage in the router (or honest legal-path search)
        Unblocks: routing creepage 431 → the 41 placement + 21 config +
        18 T1T2U6 remainder, now countable.
        Dependency: Step 2's per-net halo machinery is the natural seam
        (creepage is a superset of clearance for HV↔LV pairs); placement
        moves (4b) shrink what the legal-path search must thread.

Step 6: owner decisions (can happen in parallel at any time)
        6a. T1/T2/U6 cert-lab creepage credit (7–18 items)
        6b. Power-class coil-net reclass (199 track_width) — or route at 1.0
        6c. C2×C3 placement authorization (199 silk + 1 courtyard)
        6d. [clearance/reinforced] 2.0 vs 6.0 drift-gate family (red gate)
        Each of these is the LAST blocker for its category; none of them
        depends on routing work.

Step 7: final re-route + full DRC + fabricability gate
        Dependency: Steps 2, 3, 4, 5. The measure of "done" is a routed
        board at DRC zero under the PD3 DRU with fill applied, plus the
        drc_ceiling.json re-measurement if pcb/temper.kicad_pcb moves.
```

**Critical-path summary**: Step 0 (done) → Step 1 (re-measure) → Step 2
(width C-space, in progress) → Step 4b/5 (placement + creepage routing,
interleaved — placement first) → Step 3 (zones, parallel) → Step 7.
The **shortest wall-clock path to a fabricable board** is Steps 0→1→2→4→7
with 3 and the owner decisions running in parallel.

---

## 5. Minimum viable fabricable board

**Question**: what is the smallest set of changes that gets the *routed*
board to DRC zero under the PD3 DRU (with fill), not the full ideal?

| Tier | Change | Kills | Cumulative effect |
|---|---|---|---|
| **T1 (non-negotiable — dead shorts)** | width-aware C-space (Step 2) | ~184 shorting + 1 crossing | No shorts: the fab-blocking class is gone. ~900 clearance/mask/hole/edge items fall with the same per-net halo change. |
| **T2 (connectivity)** | zone redesign + fill (Step 3) + gnd plane (done) + T2 placement (4a) | ~54–90 unconnected | Every net either connected or honestly declared unroutable at PD3. |
| **T3 (safety geometry)** | live HV↔LV creepage with honest failure + placement moves for the 41 pad-pad + top components (Step 4b/5) | 431 routing creepage → placement/config remainder | Creepage drops to the placement + config + cert-lab residue (~60–80, of which 7–18 need the cert answer). |
| **T4 (mechanical)** | constraint-respecting re-route (edge/via/hole rules) + library sync + silk/refdes cleanup + C5×C7 | ~350 mechanical items | Everything but owner-decision residue. |
| **T5 (owner decisions)** | 6a cert-lab (7–18), 6b coil reclass (199), 6c C2×C3 (199 silk) | final residue | DRC zero. |

**Smallest fabricable set**: T1 + T2 + T3 + T4 — i.e. **no owner decisions
are required for a fabricable board** if the coil nets are routed at
1.0 mm (not reclassified) and the C2/C3 silk overlap is accepted as
non-fabricability-relevant (silk_overlap is a warning-class cosmetic issue
for most fabs; C2/C3's *courtyard* overlap is the one that matters and it
is one pair). The T1/T2/U6 cert-lab items are the only true
fabricability blockers among the owner decisions if the fab enforces PD3
creepage on the isolation barrier — which is exactly why the cert-lab
package is already drafted.

**The one decision without which nothing else matters**: none — the
dependency graph's Step 0 is done (this branch). The next concrete
artifact is the Step-1 re-measurement on the post-#1245/#1246 main.

---

## 6. What this branch changed (2026-08-16)

1. **`--net-batching` default True** (`scripts/route_board.py`, all four
   internal signatures; `--no-net-batching` opt-out added).
2. **Stage 3 auto-batch safety net** (`_pipeline_route.py`): when the
   monolithic model would exceed `_AUTO_BATCH_VAR_THRESHOLD` (2.5M raw
   vars, chosen so an attempted monolith's CNF demand stays ≤~20–25 GB;
   the initial 10M suggestion was rejected — it extrapolates to ~80–88 GB,
   an OOM by construction), `_run_stage3` routes through
   `run_net_batched_stage3` with a loud warning. Selective-SAT subsets
   (`max_sat_nets`) honor the estimate; bundling and geographic pruning
   skip the guard (their own reductions apply).
3. Measured on the production board: `--no-net-batching` (the former
   OOMing default) now logs "Stage 3 monolithic model would be
   ~35,415,254 raw variables … routing through net-batching" and completes
   — first successful no-flag route in the project's history on this
   board.
4. Tests: `tests/router_v6/test_stage3_auto_batch.py` (9 tests: estimate
   arithmetic, fires/does-not-fire decision matrix incl. explicit
   batching, pruning, bundling, selective-SAT).

## 7. Sources

- `docs/evidence/2026-08-15-drc-violation-classification.md` (agent 59)
- `docs/evidence/2026-08-15-unrouted-nets-rootcause.md` (agent 57, M1–M5)
- `docs/evidence/2026-08-15-router-honesty-audit.md` (agent 58, via-type)
- `docs/evidence/2026-08-15-rust-zone-pour-design.md` (agent 64)
- `docs/evidence/2026-08-15-router-pad-avoidance-fix.md` (agent 62)
- `docs/evidence/2026-08-15-final-board-verification.md` + `2026-08-15-full-board-route-verification.md` (agent 69)
- `docs/evidence/2026-08-15-stage3-memory-blowup-investigation.md` (agent 4)
- `docs/evidence/2026-08-15-pd2-pd3-data-driven-decision.md`,
  `docs/evidence/2026-08-15-pending-decisions.md`
- Commits: #1200, #1220/#1229, #1221, #1222, #1223, #1245, #1246, #1173,
  #1201/#1134, #1237/#1238, #1144; this branch
  (`fix/stage3-memory-and-drc-zero-plan`).
