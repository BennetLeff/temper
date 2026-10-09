# Closure review: native-21 stage 8 vs the 2026-10-08 pre-fab review

Reviewer: independent senior PCB review, read-only. Date: 2026-10-08.

**Board:** `scratchpad/s8b/section.kicad_pcb`. I re-hashed it as SHA-256 `d4468ffd…a5ba`, which matches the brief and FAB-NOTE. I compared it with the stage-7 board the original review used (`scratchpad/s7/section.kicad_pcb`, `ebdfdb3c…6124`).

**Method:** All numbers below are my own measurements, taken as follows.
- **Geometry:** KiCad 10 `pcbnew.LoadBoard`. I extracted the copper myself (pads, tracks, vias with per-layer flashing, and zone fills) into `review8/geom.json`.
- **Distances:** shapely.
- **Routed paths:** my own Dijkstra over tracks, vias and filled zones (`review8/path.py`). A hop across a zone is costed as a straight line, and `ZONE0=1` costs it at zero.
- **DRC:** I re-ran `kicad-cli pcb drc --refill-zones --schematic-parity` on a scratch copy (`review8/drc/drc-refill.json`).
- **Scripts:** `review8/*.py`.

Coordinates are in KiCad board mm. A "loop" is the routed pin → cap → pin path.

**The fab package changed during this review.** Commit `ef3bc4fac` ("F1 -> Eaton Bussmann MDA-25-R") landed at 18:13. The BOM, FAB-NOTE and F1-J3-PARTS that I quote are the post-commit versions. The board file did not change.

## Summary verdicts

| Id | Verdict | One-line evidence |
| --- | --- | --- |
| **B1** | **PARTIAL** (drop to MAJOR) | The caps exist and the VDD legs are short: VDDA→C10 4.5 mm, VDDB→C8 5.5 mm. The VSS returns are not local: U1 VSSA→C10 is **30.0 mm** with 2 vias through B.Cu, giving a leg A loop of ~39 mm perimeter and ~56 mm² (estimate ~25–30 nH). The other loops are 15–24 mm. |
| **B2** | **CLOSED** | U26, U27 and U28 each have 9 × 0.3 mm vias inside the 3.15 mm EP, on the EP net (n_ls / n_ha / n_hb). Every via lands in that net's In1 fill (603 / 1242 / 1167 mm²). U35 has 3 vias inside the EP and a 4th on its edge (n_ls). No B.Cu fill under any of them. |
| **M1** | **PARTIAL** | ISO7710 VCC1/VCC2 100 nF caps are 2.5–4.9 mm from the pins, with 2.2–6.8 mm routed legs. AMC1311 has 100 nF only: no 1 µF on either side (datasheet §10, Fig 10-1). U4 VDD1's C28 is reached through 5 vias (5.1 + 9.9 mm). |
| M2 | **NOT CLOSED** | No Kelvin return was added. Stage 8 also **rerouted the leg A gate-drive return**: the sw_a track from reservoir C50 to the Q2 source pour went from **24.1 to 44.5 mm**. This contradicts DECISIONS ("gate-loop copper the FEM extracted is untouched"). There was no re-extraction. See N1. |
| **M3** | **PARTIAL** (mostly closed) | 30 THT pads have a local THERMAL override: 0.5 mm spokes, 0.5 mm gap, and spokes visible in the fills. 82 power pads stay FULL, as intended. THR is now in FAB-NOTE. There is no selective-solder or preheat spec for factory soldering of the solid 2 oz power pins, only "hand rework". |
| **M4** | **PARTIAL** | The outer layers are copper-free inside the 7 mm washer at H1–H7 (F and B, measured). H8 is gone. H4 and H6 have **HOT In1 copper 1.20 / 1.90 mm from the hole wall**, so safety rests entirely on the nylon hardware. The 10 mm standoff is credible only if the whole fixing chain to the chassis is insulating. |
| M5 | NOT CLOSED, accepted by decision (reasonable) | The minimum is still **8.047 mm** (via leg_a-dis (75.54, 58.8) to the n_ha B.Cu zone, and the leg B mirror). There are 388 HOT↔SELV/PE pairs below 8.2 mm and 0 below 8.0 mm. |
| M6 | DEFERRED-TO-OWNER (reasonable; gates release) | J5 (132, 70.5) and J2 (132, 85.5) are unchanged at 15 mm centres. |
| **M7** | **CLOSED** | J3 pitch is **7.92 mm**. With 2.7 mm pads the copper gap is **5.22 mm**. The nearest other-group HOT copper is 4.50 mm away (tco_l to the l_f zone). |
| **M8** | **CLOSED**, with an open release gate | Clips are 2 × 01220088Z (30 A) on their own BOM line. The 25 A fuse derating checks: 25 × 0.75 × 0.96–0.97 ≈ 18 A, against 16.5 A. Two items stay open: the interrupting rating above 125 Vac (MDA-25-R, 1.5 kA at 250 Vac), and the 15 A plug vs the 16.5 A input. |
| **M9** | **CLOSED** | The CPL centroid equals the pad-bbox centre for all 351 parts (max deviation 0.00 mm). Mount type equals the footprint attribute everywhere, and T1 is SMD. Rotations are KiCad orientation; JLC's preview is now a meaningful check. |
| M10 | DEFERRED-TO-OWNER (reasonable) | The L outline and J4 at (34.5, 180.1) are unchanged. |
| M11 | DEFERRED-TO-OWNER (reasonable; gates release) | The TO-247/BR1 positions are unchanged. |
| **M12** | **CLOSED** (minor residuals) | On silk: board ID, a DANGER text, PE at J6, the BR1 outline with + ~ ~ − (pins checked), washer circles, and the nylon legend. The assembly-drawing PDF contains the stage-8 refs. The legend says "H2-H8", but H8 no longer exists. |
| M13 | PARTIAL | A buy plan exists (PROTOTYPE-LOT.md). I did not re-verify stock. |
| M14 | NOT CLOSED, accepted by decision (reasonable) | R38 is at (25.4, 132.9) and J6 at (150.6, 134.5). The leakage-only argument holds for current. Y-cap path inductance affects only EMI. |

**New findings:**
- **1 MAJOR:** N1, the leg A gate-loop copper changed without re-extraction.
- **No new BLOCKERs.**
- **MINORs:** N2–N6.

**DRC:** my own rerun with zone refill gives **0 errors, 0 unconnected, 0 parity**. It produces the same 245 warnings as the designer's drc.json:
- 199 `lib_footprint_issues`;
- 20 `silk_over_copper`;
- 13 `track_dangling`;
- 9 `silk_overlap`;
- 4 `silk_edge_clearance`.

The board hash was unchanged after the run.

---

## B1: UCC21550 VDD–VSS decoupling

**Parts and nets (board):**

| Cap | Value | Nets | Position |
| --- | --- | --- | --- |
| C10 | 100 nF 0603 | p_ha / n_ha | (74.95, 41.1) |
| C11 | 10 µF 0805 GRM21BZ71E106KE15L | p_ha / n_ha | (74.75, 37.35) |
| C17 | 100 nF | p_hb / n_hb | (27.7, 41.1) |
| C18 | 10 µF 0805 | p_hb / n_hb | (27.5, 36.6) |
| C8 | 100 nF | v15_ls / n_ls (VDDB/VSSB) | (85.4, 41.1) |
| C15 | 100 nF | v15_ls / n_ls | (38.4, 41.1) |
| C9 / C16 | 10 µF 1210 | v15_ls / n_ls | unchanged |

**Pin to cap-pad centre distances** confirm the triage:
- VDDA (pin 16): C10 4.29 mm, C11 7.87 mm, C17 4.3 mm, C18 8.64 mm.
- VDDB (pin 11): C8 and C15 5.50 mm; C9 and C16 14.5 mm.

**Routed loops** (`path.py`, shortest copper path):

| Loop | VDD leg | VSS leg | Vias | Perimeter / plan area |
| --- | --- | --- | --- | --- |
| U1 16→C10→14 (leg A HF) | 4.5 mm F.Cu 0.25 | **30.0 mm**: F.Cu 27.0 + B.Cu bank 3.1 (pin 14 runs 13.5 mm north on x = 77.83 to via (77.86, 30.85), through B.Cu to via (74.8, 30.7), then back south to C10.2) | 2 | 39 mm / 56 mm² |
| U1 16→C11→14 | 9.3 | 26.7 (same path) | 2 | 41 / 48 |
| U2 16→C17→14 (leg B HF) | 5.1 | 11.2: via (31.09, 40.0), B.Cu, then via (26.88, 40.47), whose annulus overlaps C17.2 by ~0.08 mm | 2 | 20 / 20 |
| U2 16→C18→14 | 10.0 | 15.3 | 2 | 30 / 14 |
| U1 11→C8→9 (LS A) | 12.5 (2 vias, B.Cu hop) | 6.4 (1 via) | 3 | 24 / 23 |
| U2 11→C15→9 (LS B) | 7.6 (2 vias) | 8.0 (2 vias, B.Cu bank) | 4 | 21 / 14 |
| U1 11→C9→9 (LS bulk) | 22.0 | 29.4 | 4 | — |

**Inductance:** a free-space rectangular-loop estimate (Grover, 0.071 mm equivalent radius for a 0.25 × 0.07 mm trace) gives:
- **leg A HF loop ≈ 28 nH**;
- leg B ≈ 13 nH;
- LS loops ≈ 10–13 nH;
- a 2 mm-adjacent cap ≈ 4–5 nH, for reference.

These are estimates, not extractions.

**Is it credible for a gate driver?**
- **Leg B and both LS loops are acceptable for bring-up** (10–15 nH), but not "as close as possible".
- **Leg A is not local decoupling.** The VDDA side is fine. The VSSA pin reaches C10/C11 only by a 30 mm detour through B.Cu.
  - At turn-on, the sourcing loop is C10 → VDDA → OUT → gate → sw_a → reservoir (C50: sw→n_ha) → C10.2. That loop does not pass through the VSSA pin, so the 30 mm leg does not starve turn-on.
  - At turn-off, the 6 A sink current flows OUT → VSSA → that 30 mm path → C50.2. The VSSA pin lifts by L·di/dt (≈25 nH × 0.3–0.4 A/ns ≈ 8–10 V for tens of ns) relative to C10.2.
  - The die therefore sees a VDDA–VSSA collapse during every turn-off edge. The UVLO deglitch should ride through it, but it is exactly what the datasheet's "locally decouple" text exists to prevent, and it slows turn-off.
- **Root cause:** OUTA (pin 15) leaves straight north between pins 16 and 14, so a cap on the pin-16 side cannot reach pin 14 on F.Cu. LOW-group In1 copper sits directly under the pins and C10.2:
  - bias_sw1 0.27 mm, v24_raw 0.42 mm and ocp_kelvin_n 0.45 mm from U1.14;
  - the dead leg_ret In1 stub (N3) 0.12 mm from C10.2.

  That copper blocks an n_ha via. DECISIONS states this constraint. It is real, but it is a layout choice that can be undone.
- **Remaining fix (MAJOR):** put an n_ha via at pin 14 and one at C10.2/C11.2 into the n_ha B.Cu bank, which spans 58.5–78.6 × 30.6–66.5 and so lies directly under them. That cuts the return to ~4 mm. It needs the In1 LOW tracks moved ≥ 3.2 mm, starting with deleting the unused leg_ret stub. The alternative is to accept a measured VDDA–VSSA ripple at bring-up (D4) as a gate.

## B2: exposed-pad thermal vias

| Part | EP (net, size) | Vias with centre in EP | Layers the vias tie into (same-net fill at the via) |
| --- | --- | --- | --- |
| U26 TPS7A4700 | pad 21 n_ls, 3.15 × 3.15 | **9** (0.3/0.6), on a 1.0 mm grid | F (the EP itself), In1 `n_ls LS block` (603 mm² fill). None in In2 or B |
| U27 | n_ha | **9** | In1 `n_ha island` (1242 mm²) |
| U28 | n_hb | **9** | In1 `n_hb island` (1167 mm²) |
| U35 SN6507 | pad 11 n_ls, 1.83 × 1.89 | **3**, plus 1 more at (105.125, 86.595) with its annulus on the EP edge = 4 contacting | In1 `n_ls LS block` |

- **Verdict:** CLOSED. The heat path is now EP → filled vias → a large In1 plane, which is a different class from 12 mm² of F.Cu.
- **Residuals (MINOR):**
  - There is no same-net B.Cu copper under any EP, so the B side is bare via lands. A small n_ls/n_ha/n_hb B.Cu pad under each would add spreading at no cost.
  - Task 04's U26 "162 °C" is, as its README says, a grid-sensitive pad-cell value, not a junction temperature. U26's Tj is still not quantified.
- POFV is required for all 770 × 0.3 mm vias in FAB-NOTE. The drill file has 770 × 0.30 mm + 10 × 0.80 mm vias, which matches the board.

## M1: AMC1311 / ISO7710 supply decoupling

Nearest correct-pair cap (pin centre to cap-pad centre) and routed legs (supply / ground):

| Pin | Cap | Distance | Routed legs |
| --- | --- | ---: | --- |
| U4 VDD1 (hot5) / GND1 | C28 100 nF | 3.35 mm | 5.1 mm (2 vias) / 9.9 mm (3 vias) |
| U4 VDD2 (v3v3) / GND2 | C29 100 nF | 2.53 | 1.8 / 9.4 (2 vias) |
| U9 VCC1 | C36 | 2.53 | 2.4 / 2.8 (1 via) |
| U9 VCC2 | C37 | 4.05 | 3.7 / 5.1 |
| U32 VCC1 / VCC2 | C133 / C134 | 2.53 / 2.53 | 2.4 / 2.9 ; 2.3 / 2.7 |
| U33 VCC1 / VCC2 | C137 / C138 | 4.87 / 2.70 | 5.1 (2 vias) / 3.9 ; 2.3 / 3.0 |
| U34 VCC1 / VCC2 | C141 / C142 | 2.70 / 2.70 | 3.0 (2 vias) / 6.8 (2 vias) ; 2.2 / 4.0 |
| UCC21550 VCCI (pin 3) | C7 / C14 | 8.1 | unchanged; not in M1's fix list |

- **ISO7710 (U9, U32–U34): closed.** Each pin has 0.1 µF within ~5 mm.
- **AMC1311: still short of the datasheet.** "Decoupled with a low-ESR, 100-nF capacitor (C1) parallel to a low-ESR, 1-µF capacitor (C2) … Place all four capacitors as close to the device as possible" (SBAS… §10, Fig 10-1, in `review/datasheets/amc1311`).
  - There is no 1 µF on hot5/ocp_kelvin_p or on v3v3/selv_gnd near U4. Every cap on hot5 within 55 mm is 100 nF.
  - C28's 5-via route (≈15 mm loop) is weak for VDD1.
- **Fix (MAJOR remaining):** add a 1 µF per side and route C28 on F.Cu.

## M2: gate loops (not closed; see N1)

The review's fix was a Kelvin source return beside the out trace. None was added; the triage relies on the FEM extraction.

Measured routed lengths, leg A:

| Segment | Stage 7 | Stage 8 |
| --- | ---: | ---: |
| out_h U1.15→R10 | 44.1 mm | 44.1 mm |
| gate R10→Q2.1 | 6.9 | 6.9 |
| VSSA U1.14→C50.2 | 27.7 | 29.4 |
| sw_a track, Q2 source pour→C50.1 (zone hop 0) | **24.1** | **44.5** |

That is about 103 → 125 mm of mostly 0.25 mm trace.

The best leg A matrix (01-switching-parasitics STATUS.md) gives P3 "gate high" = **24.26 nH**. That is hard to reconcile with a full U.15→U.14 loop of ≥ 100 mm of thin track. I could not confirm from the repo which conductors P3 closes through. Either way, the claim that the stage-8 edits left the extracted copper untouched is false for leg A (N1).

## M3: thermal relief

- **Zone default:** all 42 zones keep `pad_connection` FULL (spokes 0.5 / gap 0.5).
- **Pad overrides:** 30 PTH pads carry a local THERMAL override with **0.5 mm spoke width and 0.5 mm gap**:
  - J4.1–16;
  - J3.2;
  - J6.1/2;
  - C3.2 and C4.2 (pe);
  - PS1.3/4;
  - PS2.1/3/4;
  - Q2/Q3/Q5/Q6 pin 1 (gates).
- **Fills show spokes:** I sampled the fraction of a ring 0.15 mm outside each pad that lies in same-net fill:
  - J4.2 / .3 / .4 / .15: 0.29–0.39, against 1.00 at stage 7;
  - PS1.3: 0.17.
- **Solid as intended** (≥ 0.81 ring fraction, or 1.0 on the plane layer):
  - BR1;
  - C5/C6;
  - C38–C41;
  - C21–C23;
  - L1;
  - D3;
  - RV1;
  - C1/C2;
  - F1;
  - J1;
  - REDCUBEs J2/J5/J7–J10;
  - TO-247 drain and source pins.
- **Process:** FAB-NOTE now states that the REDCUBEs are THR (paste in hole).
- **Residual (MINOR):**
  - For the solid 2 oz pins assembled by JLC as THT (BR1, L1, C21–C23, D3, RV1, C1/C2), FAB-NOTE says only "need a preheated board for hand rework". The review's selective-solder + preheat + barrel-fill inspection requirement is not on the order.
  - D3, RV1 and C1/C2 are low-current parts on high-current nets and could take reliefs.

## M4: fixing holes

For each hole I took its 7 mm washer diameter and measured outer-layer copper inside it. I also measured the nearest HOT/SELV/PE copper on any layer, as a distance from the hole wall (3.2 mm NPTH).

| Hole | Centre | F.Cu / B.Cu in washer | Nearest HOT (layer) | Nearest SELV/PE |
| --- | --- | --- | --- | --- |
| H1 (metal allowed) | (285, 135) | none / none | hv_ret In1, 20.40 (outer: 26.1) | 66.6 |
| H2 | (6, 180) | none / none | n_hb In1, 59.4 | v3v3 In1 **0.25** |
| H3 | (86, 180) | none / none | 61.6 | v3v3 In1 **0.25** |
| **H4** | (24, 74) | none / none | **n_hb In1, 1.20** (outer: 5.78) | selv_gnd In2, 3.80 |
| H5 | (88, 100) | none / none | vsense_in F.Cu, 7.92 | v3v3 In1 **0.25** |
| **H6** | (128, 54) | none / none | **hv_ret In1, 1.90**; sw_b B.Cu 2.40 (0.5 mm outside the washer edge) | 40.1 |
| H7 | (194, 130) | none / none | sw_b B.Cu, 15.40 | v3v3 In1 0.25; pe F.Cu 2.80 |

**Closed:**
- The washer faces on both outer layers are copper-free. The silkscreen circles are 7.4 mm.
- H8 (SELV track 0.6 mm from the wall) was removed.
- The H6 B.Cu l_filt track is gone.

**Judgement on "nylon standoff ≥ 10 mm" at H4–H6:**
- With an all-insulating chain the mitigation is credible. HOT inner copper → laminate to the hole wall (1.2–1.9 mm) → down the nylon standoff → chassis gives more than 8 mm of creepage.
- **It does not hold** if the standoff is fixed to a metal chassis with a metal screw. A female-female standoff's bore puts that screw tip within ~10 − 2 × thread engagement of the board, roughly 2–4 mm.
- It also fails under a single assembly error: a metal M3 at H4 or H6 sits **1.2 / 1.9 mm of laminate** from HOT and is bonded to PE.
- The same holds at H2/H3/H5/H7, where SELV planes are 0.25 mm from the wall. A metal screw there makes a second SELV–PE bond.
- Silk (one legend, plus washer circles) is the only control.
- **Remaining (MAJOR, enclosure/assembly):** specify the whole chain:
  - nylon screw;
  - nylon washer;
  - a male-female or solid nylon standoff with ≥ 8 mm of solid insulation between any metal and the board, or an insulating boss;
  - a matched enclosure boss.

  Better, for H4 and H6, pull the inner HOT planes back to ≥ 8 mm, or use snap-in nylon supports that cannot take a metal screw.
- The D5-AUDIT figures differ from mine: it gives H4 0.55 mm and H5 7.26 mm, where I measure 1.20 and 7.92 mm. D5-AUDIT is the conservative one.

## M5: barrier margin (decision)

My independent plan-view minimum over all layers is **8.047 mm**. It occurs at the via leg_a-dis (75.54, 58.8) to the n_ha B.Cu zone, and at the leg B mirror via (28.54, 58.8) to n_hb. There are 0 pairs below 8.0 mm and 388 pair-records below 8.2 mm.

The rationale is reasonable for same-layer gaps: they are image-defined, and etch undercut widens them. It does not address drill-to-image registration for cross-layer plan-view pairs, though those are not surface creepage paths.

**Acceptable as an owner-approved provisional floor.** It must be revisited with the lab's final number.

**Note:** D5-AUDIT names the minimum as "zone n_ha / via leg_a-dis at [67.46, 42.32]". That is the zone's centroid; the via is at (75.54, 58.8).

## M6, M10, M11: owner deferrals

- **M6:** unchanged, J5/J2 at 15 mm centres.
- **M10:** unchanged; L outline, J4 at the tongue front.
- **M11:** unchanged; the TO-247 and BR1 positions are as at stage 7.

All three are listed in FAB-NOTE as open gates before ordering, so deferring them is reasonable. M6 and M11 are safety items and should block release, not just be recorded.

## M7: J3 (TCO loop)

- J3 is JST B2P3-VH, `JST_VH_B2P3-VH_1x02_P7.92mm_Vertical`.
- Pin 1 is l_filt at (217.65, 11.81) and pin 2 is tco_l at (217.65, 3.89). Pitch is **7.92 mm**; pads are 2.7 mm round, drill 1.7 mm.
- Copper gap: **5.22 mm**.
- Nearest other-group HOT copper on the same layer:
  - from pin 2: 4.50 mm (l_f zone);
  - from pin 1: 5.95 mm (v24_raw track).
- **CLOSED.** Unshrouded and hand-soldered, as documented. Pin 2 sits 2.54 mm from the board's top edge; check this against the sink and enclosure (M11 scope).

## M8: F1 clips and fuse

**Board:** the F1 footprint is `Fuseholder_Clip-6.3x32mm_Littelfuse_102_122_Inline_P34.21x7.62mm_D1.98mm`. It has 4 pads of 3.0 mm with 1.98 mm drills, at x 227.395 / 235.015 / 253.985 / 261.605. That gives 34.21 mm outer to outer and 7.62 mm per clip.

**BOM:**
- F1-CLIP: 01220088Z (30 A), "2 per board, hand-solder". It is not in the CPL, which is correct for a hand-placed part.
- The F1 line is now **MDA-25-R** (commit `ef3bc4fac`), while the board's F1 value field still reads 0326025.MXP. FAB-NOTE says the BOM governs. See N5.

**Derating argument (checked):**
- Littelfuse 326: 25 % continuous derating × ~97 % at 50 °C gives 20 A → 14.5 A and **25 A → 18.2 A**.
- Eaton MDA: ~96 % at 50 °C gives 25 A → **18.0 A**.
- Both exceed the 16.5 A RMS line current (108 V, 1.7 kW). At 70 °C local ambient (~93 %) it is ~17.4 A, still above.
- The arithmetic and the use of the 25 % continuous derating are correct.
- The temperature factors are read off curves. F1's local ambient should be bounded in the enclosure.

**Coordination notes:**
- A 25 A fuse does not protect the 20 A CMC or the 24 A J1 against a 20–25 A overload. That protection relies on the controller's current cap (R21 N8 / 22 A tank envelope). It is not a fuse function.
- The 15 A plug vs 16.5 A input choice is pending with the owner.

**Verdict:** CLOSED for the review finding: clips present and rated, fuse up-rated. The interrupting rating above 125 Vac (MDA-25-R is 1.5 kA at 250 Vac) and the plug/current cap are open release gates. FAB-NOTE lists them.

## M9: CPL

- `cpl-jlcpcb.csv` Mid X/Y matches the pad-bounding-box centre for every one of the 351 parts. The maximum deviation is 0.00 mm. PS1/PS2 are now 24.79 mm from their KiCad origins, C5/C6 21.32 mm, F1 17.11 mm.
- Mount column: SMD 317, THT 34. It matches each footprint's SMD/THT attribute with no mismatches, and T1 is SMD.
- Rotation equals the KiCad orientation for all parts. No JLC offset table exists; FAB-NOTE delegates rotation to JLC's preview, which is now meaningful.
- **CLOSED.**

## M12: marking and assembly drawing

**On F.Silkscreen:**
- "TEMPER POWER STAGE 120V / NATIVE-21 REV A 2026-10" at (274, 122), 1.5 mm / 0.225 mm;
- "DANGER: MAINS AND 400 V DC / HOT SECTIONS ARE NOT EARTHED" at (136, 46);
- "PE" at (158, 128) beside J6 (150.6–165.8, 134.5);
- a BR1 rectangle (78.1–110.3 × 0.9–8.7) with "+ ~ ~ −" at x 81.7 / 91.7 / 99.2 / 106.7, which match BR1 pads 1 rect_p, 2 l_filt, 3 n_filt and 4 rect_n;
- six 7.4 mm circles at H2–H7;
- a legend "H2-H8: NYLON SCREWS, WASHERS AND STANDOFFS ONLY" at 1.0 mm / 0.15 mm stroke.

**Assembly drawing:** `fab/assembly-drawing.pdf` (PCBNEW) contains C10/C11/C17/C18, the TPs, NYLON ×7, and so on, so it is a stage-8 export.

**Verdict:** CLOSED. Residuals are in N2.

## M13, M14

- **M13:** PROTOTYPE-LOT.md has a buy plan covering the zero-stock lines. Stock was not re-verified: PARTIAL.
- **M14:** R38 is at (25.4, 132.9); J6 at (150.6, 134.5). The functional-bond reasoning (Y-cap leakage only) holds for current. The extra Y-cap path inductance is an EMI question only (it lowers CM-filter effectiveness above ~10 MHz). Acceptable as a recorded decision.

## Stage-8 regression spot-checks

**Barrier near the new and moved caps** (plan view, all layers, to the nearest SELV/PE copper):

| Parts | Distance to SELV/PE |
| --- | --- |
| C10 / C11 / C17 / C18 | 12.73 / 16.25 / 12.73 / 17.01 mm |
| C8 / C15 | 12.74 mm |
| Moved isolator caps, HOT side (C28, C36, C133, C137, C141) | 9.32–10.97 mm (min C137.1 at 9.32 to selv_gnd F.Cu) |
| Moved isolator caps, SELV side (C29, C37, C134, C138, C142) | ≥ 10.87 mm to HOT |
| TP31 (moved) | 8.48 mm (pwm_ha) |
| TP32 / TP9 | 9.10 / 9.20 mm |
| Board minimum | 8.047 mm, as at stage 7 |

The closest new copper is the p_ha track to U1 pin 1 (pwm_ha) at 8.05 mm.

**3.2 mm HOT-group spacing around the new parts** (same layer, other group, excluding the same footprint's own pads):

| Parts | Nearest other-group HOT copper |
| --- | --- |
| C10 / C11 | ≥ 5.78 mm (v15_ls via, LOW) |
| C17 / C18 | ≥ 6.28 mm |
| C8 / C15 | ≥ 6.34 mm |
| R71 / R74 | ≥ 6.41 mm |
| J3 | ≥ 4.50 mm |
| F1 | ≥ 4.61 mm |

Board-wide, 20 same-layer group/tank pairs are under their figure. All are tracks entering the two pads of one 2-terminal bridging part (C12/C13/C19/C20 snubbers, divider and bleeder chains) and existed at stage 7. The project's .dru carries area exemptions for these, and none is near the stage-8 edits.

**DRC errors:** none, in both the designer's drc.json and my refilled rerun.

**13 dangling tracks:** 12 are ≤ ~3 mm jog or overlap stubs from patch editing (largest dead ends: sw_b F.Cu chain ~0.14–3.2 mm, hot5 F.Cu 1.0 mm). The 13th is not short (N3).

## New findings

- **N1 — MAJOR — Stage 8 changed leg A's high-side gate-drive return copper. No re-extraction was done, and the DECISIONS statement is wrong.**
  - Moving R71 and the n_ha column into the old corridor (x 72.4–73.5, y 29.8–37.5) forced the sw_a link from the bias reservoir (C50/C51 1 µF, C110–C113) to Q2's source pour into a detour west to x 59.9 and back.
  - That link is **44.5 mm of 0.25 mm F.Cu, against 24.1 mm of 0.25–0.30 mm at stage 7**: 35 sw_a segments removed, 62 added. The direct 0.3 mm n_ha diagonal (74.8, 30.7)→(72.375, 39.6) was also replaced by a 0.25 mm zig-zag through C11/C10.
  - DECISIONS says "off the four OUT gate lanes, so the gate-loop copper the FEM extracted is untouched … the loops were not re-extracted". The OUT lanes are untouched; the return half of the leg A loop is not.
  - **Fix:** re-extract P3 for leg A and re-run F6, or restore a short, wide sw_a link. Ideally, also do the B1 via fix, which shortens VSSA.
- **N2 — MINOR — Silk legend and labels.**
  - The legend reads "H2-H8", but H8 was removed.
  - Per-hole "NYLON" text is on F.Fab only, not on silk as the triage says.
  - DRC flags the board-ID text for silk-to-edge clearance and for overlapping PS1's silk.
  - The H2–H7 refdes overlap their washer circles.
  - The legend stroke is 0.15 mm (JLC minimum; review m12).
- **N3 — MINOR — The 36 mm dead leg_ret In1 stub (review m1) is still there, and FAB-NOTE calls all 13 dangling items "short".**
  - The stub runs (55.6, 40.0)→(91.6, 40.0) to the first via, with a duplicate overlapping segment (55.6→95.4 over 55.6→110.0).
  - It passes 0.12 mm (plan) under C10.2 and is one of the In1 obstacles that kept the B1 n_ha via out.
  - Delete it.
- **N4 — MINOR — U26–U28 / U35 have no same-net B.Cu land under the thermal vias.** Free extra spreading.
- **N5 — MINOR — The F1 identity is inconsistent across the package.** The board value and `positions-kicad.csv` say 0326025.MXP; the BOM, source and F1-J3-PARTS say MDA-25-R. FAB-NOTE acknowledges this ("the BOM governs"). The next rebuild must carry the change through, or JLC will see two values.
- **N6 — MINOR — D5-AUDIT text errors.**
  - The location of the barrier minimum quotes a zone centroid, not the via.
  - The H4/H5 hole-wall distances (0.55 / 7.26 mm) disagree with my 1.20 / 7.92 mm.

## What I did not check

- Gerber/drill files against the board, beyond the drill-report counts (770 + 10 vias match).
- The FEM model's port topology (M2/N1). This is why N1 is stated as a copper change, not an inductance number.
- Footprint land patterns for the new 0805/0603 caps, J3 and the F1 clips against the maker drawings.
- Stock.
- Thermal values.
- Sink and enclosure geometry.
