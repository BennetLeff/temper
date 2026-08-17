---
module: pcb
tags: [drc, routing, classification, creepage, clearance, zone-fill]
problem_type: measurement-and-triage
date: 2026-08-15
---

# DRC Violation Classification — 6-Layer Routed Board (2026-08-15)

**Purpose**: classify every DRC violation on the routed 6-layer board into a fix
path (routing / placement / component / config / zone-fill / board-defect), so
the project has a complete, prioritized action list to drive DRC to zero.

## 1. What was measured

| | Board | DRU | kicad-cli |
|---|---|---|---|
| Routed | `/tmp/opencode/final-route-6layer-output.kicad_pcb` (97/107 nets routed, 6012 segments, 74 vias, 231 zones) | `final-route-6layer-output.kicad_dru` (PD3, 12.6 mm reinforced creepage) | 10.0.5 |
| Committed | `pcb/temper.kicad_pcb` @ origin/main (`2c1f112a6`, sha `b2ae6c66…`) | same DRU (copied beside project) | 10.0.5 |

Both boards have **identical component placement** (verified: 0 footprints at
different positions) — every delta is the router's tracks/vias/zones. Both were
DRC'd with `--all-track-errors`, single-threaded, JSON output, project context
resolved (`.kicad_pro` + `.kicad_dru` beside each board, fp-lib-table present).
Routed board also measured **with `--refill-zones`** to test the zone-fill
hypothesis (section 4).

**Saturation caveat**: KiCad caps per-rule reporting at ERROR_LIMIT 199 /
EXTENDED_ERROR_LIMIT 499 (AGENTS.md §2.4). Categories landing exactly on
199 or 499 are **lower bounds, not exact counts**: `track_width` 199,
`hole_clearance` 199, `silk_overlap` 199, `clearance` 499.

## 2. Headline totals

| Metric | Committed | Routed (unfilled) | Routed (filled) |
|---|---|---|---|
| Total violations | 1853 | 2248 | 2120 err + 519 warn |
| Unconnected items | 425 | 329 | 326 |
| **Grand total** | **2278** | **2577** | **2965** |

The router **reduced unconnected items by 96** (425 → 329) but **increased
creepage 323 → 511** (+188, tracks/vias routed into HV↔LV zones) and
**hole_clearance 92 → 199** (vias too close to holes). It also introduced
**shorting_items 196 → 204** and **solder_mask_bridge 146 → 208**.

## 3. Per-category classification (routed board, unfilled — the router's output)

| # | Category | Count | Sub-breakdown | Fix path | Specific action | Difficulty |
|---|---|---|---|---|---|---|
| 1 | **creepage** | **511** | 431 routing (pad-track 381, track-track 31, pad-via 28, track-via 9 → minus 18 T1T2U6) · 41 placement (pad-pad, diff comps) · 21 config same-footprint (U6×7, K2×4, K3×4, R51, R46, C6, U5, R15, R30) · 18 routing T1T2U6-involved · (7 of the 21 same-footprint are T1/T2/U6 pad-pad = cert-lab question) | routing 449 / placement 41 / config 21 | Router must keep HV↔LV creepage (12.6 mm PD3) when routing; move U6/K2/K3-neighbour parts; fix same-footprint rules | **hard** (routing under 12.6 mm is the board's fundamental constraint) |
| 2 | **clearance** | **499** ⚠ sat | 187 Default routing · 143 HighVoltageSignal→LV · 105 HV→LV · 31 HVIsolated same side · 15 HVTank→LV · 9 netclass · 9 AC→LV. All items are track/via vs track/pad | **routing 499** | Router respects clearance (0.2–2.0 mm by rule); most are tracks routed too close to pads/tracks | moderate |
| 3 | **unconnected_items** | **329** | 272 pure-routing (gnd 87, +3V3 49, vcc 13, +15V 10, I_SENSE 5, refin_n 5, SHUTDOWN 4, …) · 57 on zone-covered nets (PWR_RTN 15, +170V_BUS 12, DC_BUS_RTN 9, SW_NODE 6, ac_n 3, …) — **but only 3 of these 57 actually resolve on real fill** (see §4) · **5 = OCP-02/T2** (T2's gnd/hb-gnd/s1 pads + s1 net) | routing 272 / **component 5** / zone-redesign 54 | Route the 272 (incl. gnd — has **no zone anywhere**; +3V3 — router dropped its zones); place T2 (OCP-02 CT, off-board at (100,300)) | moderate |
| 4 | **track_width** | **199** ⚠ sat | ALL rule "Power trace width" min 1.0 mm, actual 0.2 mm. Nets: discharge.k_dis2-coil1 (104), k_dis1-coil2 (53), k_dis1-coil1 (42) — classed **Power** in `.kicad_pro` but routed at 0.2 mm | routing (router width) / config (reclass) | Route these three coil-drive nets at 1.0 mm, or reclass them to FinePitch (they are relay coils; 0.2 mm may be adequate) | trivial–moderate |
| 5 | **shorting_items** | **204** | pad-track 110 · track-track 63 · track-via 31. **REAL SHORTS, not artifacts**: router routed tracks **through** pads of other nets (w1_1 track through RV1's ac_n PTH pad; w1_2 track through C1's w1_1 pad; 27 pairs involve w1_1) | **routing 204** (router bug) | Router must never route a track through/over a pad of a different net; w1_1 (HighVoltage) is the worst offender | **hard** (router core bug) |
| 6 | **solder_mask_bridge** | **208** | all pad-track — router tracks within mask-expansion distance of pads of other nets (U16 40, U9 38, U27 10, R51 10, …) | routing 208 | Re-route tracks clear of pads; or mask-expansion config | moderate |
| 7 | **hole_clearance** | **199** ⚠ sat | track-via 153 · pad-track 44 · other 2. Router vias too close to holes (RT1 11, U5 7, U4 6, RV1 3, R1 3 pads) | routing 199 | Router via placement must respect hole clearance (0.25 mm) | moderate |
| 8 | **silk_overlap** | **199** ⚠ sat | ALL C2/C3 silkscreen (2 refs) — the two big THT caps sit close enough that their silk overlaps | placement 199 | Move C2 or C3 (their courtyards also overlap — see #13) | trivial |
| 9 | **silk_over_copper** | **61** | C4 21, R4 21, U19 10, C12 4, … ref-fields/pads over copper | board-side silk fix 61 | Move reference designators off pads (footprint silk edit) | trivial |
| 10 | **copper_edge_clearance** | **44** | discharge.k_dis2-nc 11 · power_in.ntc-no 11 · RTD_DRDY 11 · uvlo mon-outa 5 · +15V_LS 3 · DC_BUS_RTN 2 · tank 1. Tracks 0.1–0.4 mm from edge vs 0.5 mm required | routing 44 | Router must keep 0.5 mm from board edge | trivial |
| 11 | **track_dangling** | **34** | B.Cu 27, F.Cu 7 — dangling stubs (0.09–0.14 mm) | routing 34 | Route cleanup (remove stubs / finish connections) | trivial |
| 12 | **holes_co_located** | **14** | via inside THT pad, same net (R60, K2, R7, R8, R9, …) | routing 14 | Router must not place via inside a PTH pad hole | trivial |
| 13 | **courtyards_overlap** | **8** | R4/C4 · K3/C3 · L1/C5 · C22/C4 · C2/C3 · C2/PS1 · C4/R46 · C5/C7 | **placement 8** | Move the 8 pairs apart (courtyard clearance) | moderate |
| 14 | **via_diameter** | **6** | all RTD_SDO vias: 0.4 mm dia vs 0.5 min | routing/config 6 | Router via sizing — use ≥0.5 mm dia for this net | trivial |
| 15 | **drill_out_of_range** | **6** | same 6 vias: 0.2 mm drill vs 0.3 min | routing/config 6 | via drill ≥0.3 mm | trivial |
| 16 | **annular_width** | **6** | same 6 vias: 0.1 mm annular vs 0.15 min | routing/config 6 | via annular ≥0.15 mm | trivial |
| 17 | **tracks_crossing** | **2** | safety.ovp.r_div_top2-p2 × +170V_BUS; w1_1 × ac_n — same-layer crossings = **shorts** | **routing 2 (router bug)** | Router must never cross same-layer tracks | hard (same root as #5) |
| 18 | **via_dangling** | **2** | RTD_SDO vias connected on one layer only | routing 2 | Finish/remove | trivial |
| 19 | **lib_footprint_mismatch** | **26** | C2, C24, C3, C37, C4, … footprints differ from library copies | config 26 | Re-sync footprints from library (or update library) | trivial |
| 20 | **lib_footprint_issues** | **13** | missing libraries: temper 9, Fuse 1, Connector_JST 1, Inductor_SMD 1, Resistor_THT 1 | config 13 (env) | fp-lib-table resolution / library presence | trivial |
| 21 | **missing_courtyard** | **5** | F1, L2, R30, RT1, U27 footprints have no courtyard | config 5 | Add courtyard to the 5 footprints | trivial |
| 22 | **silk_edge_clearance** | **1** | TP4 ref field at board edge | board-side 1 | move TP4 silk | trivial |
| 23 | **pth_inside_courtyard** | **1** | C7 PTH pad inside C5 courtyard | placement 1 | move C7 or C5 | trivial |

### Unconnected items detail (329)

- **Zone-covered nets** (57): PWR_RTN 15, +170V_BUS 12, DC_BUS_RTN 9, SW_NODE 6,
  ac_n 3, tank.c_tank1-p2 3, w1_1 3, power_in.ntc-no 3, w1_2 1, tank-out 1,
  ac_l 1. These nets **do** have zones, but see §4 — only 3 actually connect
  when filled.
- **Pure routing** (272): dominated by **gnd 87** (has **no zone on either
  board** — net 48 appears in no zone declaration) and **+3V3 49** (the router
  **dropped** the committed board's 34 +3V3 zones). Both were in the router's
  honest-gap list (`+3V3, RELAY_CTRL, fb, gnd, i2c_sda_ui, power_in.q_relay_drv-g,
  s1, safety.fault_or-y2, sdi, sdo` — 10 nets, 136 items) plus another ~136
  items on nets the router "fake-completed" (copper exists but does not join all
  pads).
- **Missing component** (5): T2 (OCP-02 CT) sits off-board at (100,300) — the
  KiCad default — with pads on gnd / hb-gnd / s1 (3 items) plus 2 more s1-net
  items (R65–C37, U19–R65). **T2 is the OCP-02 current transformer, never
  placed.** (Also 1 item: OCP2_VREF_2V5 stub, 1: safety.ocp2-line stub.)

## 4. Zone-fill test — the "fill will fix it" hypothesis FAILS

Ran DRC on the routed board with `--refill-zones --save-board`:

| Category | Unfilled | Filled | Delta |
|---|---|---|---|
| creepage | 511 | **733** | **+222** (zone copper violates HV↔LV creepage: 309 zone-involved, e.g. +170V_BUS pour 2.0 mm from +3V3 pad of U16) |
| isolated_copper (warn) | 0 | **167** | **+167** — pours fragment: PWR_RTN 45, power_in.ntc-no 25, DC_BUS_RTN 23, ac_n 16, +170V_BUS 14, SW_NODE 14, … |
| clearance | 499 | 501 | +2 |
| shorting_items | 204 | 205 | +1 |
| unconnected | 329 | **326** | **−3 only** (PWR_RTN/SW_NODE/etc. items do NOT resolve — pads sit in different islands of the fragmented pour) |

**Conclusion**: the "zone-fill-needed" bucket is effectively **dead on this
board**. The router's 231 zone definitions fragment under real KiCad fill into
167 isolated islands; filling connects only 3 of the 57 zone-net unconnected
items and *adds* 222 creepage violations (HV pours poured right up against LV
pads). The correct action is **zone redesign** (single-hull pours that cover the
target pads and keep 12.6 mm creepage from LV), not "fill zones and re-run".
This corroborates handoff §8.6 (`power_in.ntc-no` pour fragments into 47+
islands).

## 5. Summary by fix path (routed board, unfilled = router's output)

| Fix path | Count | Categories |
|---|---|---|
| **Routing-fixable** | **~2140** | creepage 449, clearance 499, shorting 204, track_width 199, solder_mask 208, hole_clearance 199, copper_edge 44, track_dangling 34, holes_co_located 14, tracks_crossing 2, via_dangling 2, via sizes 18 (6 dia + 6 drill + 6 annular), unconnected-routing 267 |
| **Placement-fixable** | **~50** | creepage placement 41, courtyards_overlap 8, pth_inside_courtyard 1 |
| **Silk / board-side cosmetic** | **~261** | silk_overlap 199, silk_over_copper 61, silk_edge 1 |
| **Config / DRU / library** | **~65** | creepage same-footprint 21, lib_mismatch 26, lib_issues 13, missing_courtyard 5 |
| **Missing component (OCP-02/T2)** | **5** | unconnected on T2 pads + s1 net |
| **Zone redesign + fill** | **54** | unconnected on zone nets (3 of 57 resolve as-is) |
| **Genuine board defect / cert question** | **7** | T1/T2/U6 same-footprint pad-pad creepage (isolation-barrier credit — needs cert-lab answer, not a re-route; these 7 are inside the 21 config same-footprint count, listed here for the owner decision) |

> Note on the config bucket: `track_width` is listed under routing but has a
> legitimate config alternative (reclass the three coil nets out of Power).
> The 18 via-size violations are router via-selection (routing) with a config
> escape (relax board-setup minimums — **not recommended**, that is a
> manufacturing rule, and the handoff forbids weakening checks).

## 6. What the ROUTER can fix by re-routing (with better constraints)

1. **Never route through pads of another net** — fixes shorting_items 204 +
   tracks_crossing 2. This is a **hard router-core bug**: it routed w1_1 tracks
   through RV1's ac_n PTH pad and w1_2 through C1's w1_1 pad. It is the single
   most dangerous defect on the board (dead shorts) and must be fixed before any
   fab.
2. **Respect clearance in the live clearance gate** — fixes clearance 499 and
   most of solder_mask_bridge 208 (tracks too close to pads).
3. **Respect netclass track width** — fixes track_width 199 (Power class routed
   at 0.2 mm instead of 1.0 mm). **Already in progress** for FinePitch
   (0.127 → 0.2); the remaining 199 are Power-class width.
4. **Respect via/hole rules** — fixes hole_clearance 199 (vias too close to
   holes) + holes_co_located 14 (via in PTH pad) + via_diameter/drill/annular 18
   (RTD_SDO vias under minimum).
5. **Keep 0.5 mm from board edge** — fixes copper_edge_clearance 44.
6. **Clean up dangling stubs** — fixes track_dangling 34 + via_dangling 2.
7. **Route the 10 honest-gap nets + the ~136 fake-completion items** — fixes
   272 unconnected (needs gnd and +3V3 zones restored first — see §7).
8. **HV↔LV creepage in the router's constraint set** — the 449 routing creepage
   violations all came from the router routing into HV↔LV zones. The router has
   a creepage-aware clearance gate (`router_clearance.rs`, PR #1198 material);
   it must be live for these pairs. This is the hardest routing item: 12.6 mm
   PD3 creepage is the board's defining constraint.

## 7. What needs PHYSICAL / non-router changes

- **Component placement** (creepage 41 + courtyards 8 + pth 1 + silk C2/C3 199):
  move the 8 courtyard-overlapping pairs (R4/C4, K3/C3, L1/C5, C22/C4, C2/C3,
  C2/PS1, C4/R46, C5/C7) and the ~41 pad-pad creepage pairs (e.g. U27–R5,
  RT1–U24).
- **Board outline / edge** — none needed; the 44 copper_edge items are tracks,
  not the outline.
- **Missing component**: **place T2 (OCP-02 CT) on-board** — it is off-board at
  (100,300) with nets on 4 pads; 5 unconnected items trace to it. (The board
  also has 3 stubs on OCP-02 nets: OCP2_VREF_2V5, safety.ocp2-line, s1.)
- **Zone redesign** (not fill): rebuild the 231 pours as single-hull fills that
  (a) cover their pads, (b) keep 12.6 mm creepage from LV, (c) **add gnd and
  +3V3 pours** (gnd has none anywhere; +3V3's were dropped by the router).
- **T1/T2/U6 isolation** (7 pad-pad creepage): cert-lab question — PD3
  island-slot creepage credit. **Owner decision, not a re-route.**

## 8. Prioritized fix list (max violation reduction, min effort)

| Pri | Action | Fixes | Est. effort | Rationale |
|---|---|---|---|---|
| 1 | **Router: never route through foreign pads / never cross layers** | 206 (204 short + 2 crossing) | hard (core) | Dead shorts — fab-blocking. Non-negotiable. |
| 2 | **Restore gnd +3V3 zones; single-hull zone redesign** | ~200 unconnected (87+49+54) − 3 + prevents 222 fill-creepage | hard (zone gen) | Biggest single reduction; unblocks everything downstream of gnd. |
| 3 | **Route the honest-gap + fake-completion nets** | 272 unconnected | moderate | After zones exist, the remaining 136 are plain routing. |
| 4 | **Router: respect netclass width (Power 1.0 mm)** | 199 track_width | trivial–moderate | Pure config/routing fix. |
| 5 | **Router: clearance + via/hole + edge constraints live** | 499 clearance + 208 mask + 199 hole + 44 edge + 14 co-located + 18 via-size | moderate–hard | The bulk of the error count (≈982). |
| 6 | **Router: creepage live for HV↔LV pairs** | 449 creepage | hard | The defining safety constraint; needs legal-path search under 12.6 mm. |
| 7 | **Place T2 (OCP-02)** | 5 | trivial–moderate | Missing component; also enables s1/OCP2 nets. |
| 8 | **Placement: courtyard + pad-pad creepage moves** | 8 + 41 + 1 | moderate | Physical moves; needs re-place then re-route. |
| 9 | **Silk cleanup (C2/C3 apart, refs off copper)** | 199 + 61 + 1 | trivial | Cosmetic but 261 items. |
| 10 | **Library sync (footprints, courtyards, libs)** | 26 + 13 + 5 | trivial | Config cleanup. |
| 11 | **Same-footprint creepage rules** | 21 (incl. 7 T1T2U6) | moderate | Rule precision; the 7 T1T2U6 need the cert-lab answer first. |

## 9. The path to DRC-zero (sequence)

1. **Fix the router's pad-avoidance bug** (shorting 204 + crossing 2). Without
   this, every re-route re-introduces dead shorts. → **206 items gone**.
2. **Redesign zones** (gnd +3V3 pours, single-hull, creepage-aware). Fill then
   resolves unconnected rather than creating +222 creepage + 167 islands. →
   **~54 zone items + 87 gnd + 49 +3V3 gone**; prevents the fill-creepage wave.
3. **Route the remaining nets** (honest-gap 136 + stubs 34 + via 2 + T2 5) →
   **unconnected → 0**.
4. **Re-route with live clearance/width/via/edge constraints** → clearance 499,
   track_width 199, hole_clearance 199, mask 208, edge 44, co-located 14,
   via-size 18 ≈ **~982 gone**.
5. **Re-route with live HV↔LV creepage** (or a legal-path search that fails
   honestly) → creepage 449 gone; the remainder of creepage (41 placement +
   21 same-footprint + 7 cert) is now visible and countable.
6. **Placement pass** (courtyards 8, pad-pad 41, pth 1, C2/C3 199 silk) →
   ~250 gone.
7. **Library/config cleanup** (26+13+5) → 44 gone.
8. **Owner decisions**: T1/T2/U6 island-slot creepage credit (7 items) and the
   PD2-vs-PD3 figure (12.6 mm vs 8.0 mm governs) — the final ~7–150 items
   depend on the certification-lab answer, not on routing.

**Honest bottom line**: DRC-zero is achievable in principle, but **not by
re-routing alone**. The two hard prerequisites are (1) the router's
pad-avoidance fix (dead shorts) and (2) a zone redesign that actually connects
gnd/+3V3 and respects creepage — the current pours fragment and create
violations when filled. After those, the count is dominated by clearance/
width/via/edge constraints that a constraint-respecting re-route clears, with
the T1/T2/U6 cert question as the only items that need an owner, not an agent.

## 10. Method notes

- Fresh DRC runs (2026-08-15, kicad-cli 10.0.5): `classify-routed-6layer.json`,
  `classify-committed.json`, `classify-routed-6layer-filled.json` in
  `/tmp/opencode/`. Single-threaded via `_drc_api.py` conventions; both boards
  share the same DRU; fp-lib-table present for both (the routed board's first
  run without fp-lib-table inflated `lib_footprint_issues` to 168 — re-run with
  library context gives 13, matching the committed board).
- The handoff's "510 routed / 323 committed" creepage matches our 511/323
  (single-sample vs their campaign's 510).
- Designator caveat (handoff §6): U6 here is the SOIC16W_Isolated gate driver
  (UCC21550-class); on other branches U6 is an IGBT. Identification is by
  footprint throughout.
