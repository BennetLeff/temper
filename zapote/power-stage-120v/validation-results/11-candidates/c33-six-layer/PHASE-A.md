# Candidate 33 phase A: stage 32 on six layers (2026-10-14)

Same outline, placement and parts as stage 32 (board 2fb346dc). The board is re-routed on JLC's 6-layer 1.6 mm, 2 / 2 oz
build and scored against s32 on one depth basis (DECISIONS 38: `F8_Z=stackup`, `SHEET_BARREL=stackup` for both boards).
**Result: ACCEPT.** Every gate holds. The scorecard is better on six metrics and worse on none against 19c, against s32 as
committed, and against s32 restated on the stack basis. Parts and BOM are identical.

## 1. Layer plan (`native-21/stackup-6L.json`)
The stack is `stackup-6L-proposed.json` (JLC061622-1080A) plus KiCad ids and copper z. Plane roles stay as on four layers.
| layer | role |
|---|---|
| F | parts, power (as today) |
| In1 | today's In1 roles: hv_ret, leg_ret, n_ha, n_hb, n_ls, ocp_kelvin_p, v3v3 |
| In2 | bus_p, selv_gnd (today's In2). bus_p / hv_ret are now the 0.30 mm core pair (was 0.5 mm) |
| In3 | signal; plus a bus_p image under the bridge |
| In4 | images of v3v3, n_ha, n_hb, n_ls, ocp_kelvin_p. B runs see the same reference as F runs over In1, so an F-B via becomes a same-net stitch. No hv_ret / bus_p image, so no plane sits under the switch nodes on B |
| B | power, signal (as today) |

**Screens on the s32 fills** (`layer_plan_screen.py`, `screens/plan-screen.json`, tightened stitch rule, before stitch vias).
Return-path open changes: 4L 18; A0 (six layers, no images) 18; **A 15**; A2 (SELV pair swapped) 17; A3 17; B (PLAN.md's
F / In1 / In2 sig / In3 sig / In4 plane / B) 18.

**Loop screen** (`loop_screen.py`, `screens/loop-screen-*.json`). This is the round-1 plane-pair formula, plane-pair term
only. It covers part of the FEM 37.6 / 24.5 nH; package, ESL and pins are not modelled.
| plan | pair gap | plane-pair term A / B leg | via F->In1 / F->bus plane | sw-node pF (sw_a + sw_b) |
|---|---|---|---|---|
| 4L s32 | 0.5 mm | 3.20 / 1.85 nH | 0.240 / 0.715 nH | 91 + 212 = 303 |
| 6L-A, s33 as built (b2) | 0.30 mm | 1.92 / 1.11 nH (**-1.28 / -0.74**) | 0.092 / 0.355 nH | 155 + 157 = 312 |
| 6L-B | 0.953 mm | +2.90 / +1.67 nH | | sw_b 375 |

Plan B puts the bus pair 0.95 mm apart. It is rejected on loop inductance alone. **Plan A was chosen.**

## 2. Routing (`passes33.sh`, `runs-native21/s33/q4`)
- Routing from `copper_base` with `passes.sh` (p2, p3) stuck at 4 unconnected. Router variance: once the In4 images
  joined the clusters, zone islands were skipped.
- **The frozen base works.** `INCR21_FROZEN=1` takes stage 32's routed copper.json (d6f55dfe) as the base. It adds only
  `patches21.add_stage33`:
  - image pours, cut 1 mm round B / In3 runs of asserted nets whose expected return differs; pieces with no via or THT
    anchor are dropped;
  - the `S33_STITCH` vias.

  It then routes the open pairs on the four routing layers first (`ROUTE4`), with In3 as the last fallback.
- q4/j1: **0 unconnected, 0 errors** in one pass. Copper: `copper-s33.json`, 719 vias (s32 710).
- Build 1, without the In3 bus_p image, failed only task 04: the BUS_P pitch span was 3.172 % against 3 %. The shorter
  F-In2 barrels cut R from 1.567 to 1.400 mOhm, but the absolute spread stayed at 0.044 mOhm. The In3 bus_p image fixes
  it: 2.62 %.

## 3. Chain (`chain33.txt`; `runs-native21/s33/b2`, board 710c0a45)
CHAIN_DONE with every gate clean.
- D5 8.047 / 8.507 mm; Rust barrier 0; RES_A outer 13.375 mm.
- DFM PASS; bypass PASS; return path PASS; fit 401 0 0 403 0.
- Task 04: 39 scenarios, 0 failed, bus_p span 2.62 % (s32 restated 2.85).
- B3 nominal_h10 / nominal_h25 / extreme_h10 / c28_h10 / c28_h25 = 155.1 / 125.3 / 240.9 / 174.4 / 129.3 °C (s32 restated
  162.0 / ... / 134.9).
- Kelvin R35.2 transfer 150.50 mOhm (s32 restated 152.83); band 67.79-116.44 A.
- Necks 0.993 (`s33_necks.json`).
- OCP pickup 3.72 A (`result-s33.json`; s32 restated 4.13 A, committed card 4.17 A).
- ZIP dd592045, kept here as `native-21-gerbers-s33-6L.zip` for a 6-layer Gerber quote.

## 4. Scorecard (`scorecard-native21s33.json`)
- vs 19c: ACCEPT. Cheaper: parts, placements, hand / consign lines, consign lines, zero-stock lines. Better:
  return_path_open_changes, return_path_worst_asserted_mm, kelvin_band_low_A, b3 x2, cmti, fuse ratio, bank ratio x2, OCP.
- vs s32 committed and vs s32 stack basis (`scorecard-native21s32-stackbasis.json`): ACCEPT, nothing cheaper (BOM
  identical). Better:
  - return-path open changes 18 -> **8**;
  - worst asserted 2.72 -> **2.38 mm**;
  - Kelvin band low 67.77 -> 67.79 A;
  - B3 c28_h25 134.9 -> **129.3 °C**;
  - nominal_h10 162.0 -> **155.1 °C**;
  - OCP pickup 4.13 -> **3.72 A**.

The 8 open changes left (`return-path33.json`), none with a pour within reach:
- bus_fault_hot (113.635, 114.5) and (100.6, 114.0);
- bias_good (69.2, 127.0), and (74.0, 123.4) at 5.09 mm (no legal stitch spot within 2.95 mm);
- mon_good_ha x4.

## 5. Bare board (instant quote, `jlc-quote-2026-10-14.json`)
| | per board at 500 | at 5 | build time |
|---|---|---|---|
| 6 L, POFV free | **$16.18** | $196.59 | 10-11 days |
| 4 L, POFV (today) | $16.79 | $214.36 | 5-6 days |

- 6 L saves $0.61 per board at 500 and $17.77 at 5. It costs about 5 more days of build time.
- **To confirm:** the inner-copper line read the same at 4 and 6 layers. Upload the s33 ZIP for a 6-layer Gerber quote.
- The quote is TG135. JLC does not name the 6-layer laminate; S1000-2M TG170 is orderable.

## 6. Not verified / left open
- **Loop inductance:** only the plane-pair screen (-1.28 / -0.74 nH). It needs FEM re-extraction (the round-1
  37.6 / 24.5 nH set-up on the six-layer copper).
- **Switch-node capacitance:** the screen gives 303 -> 312 pF (+3 %). sw_a rose from 91 to 155 pF (the F-In1 prepreg is 0.22 mm on six layers).
  sw_b fell from 212 to 157 pF; on build 1 it was 101 pF, and the In3 bus_p image adds back about 56 pF. This is not a
  scorecard metric. EMI (`emi_min_margin_dB`, s19b) and touch leakage were not re-run for the stack.
- **Safety basis:** D5 / barrier / RES_A gates pass on the six-layer geometry. The CTI / solid-insulation inquiry for
  JLC061622-1080A (PLAN step 1) has not been re-asked.
- **30b not closed.** C161's via at (99.5, 95.035) reaches the In1 n_ls plane only through about 4.5 mm of In1 track. The
  In4 n_ls image is cut there under bus_fault_hot's B run to keep SI1. The bypass limit stays 6.0.
- **30a not attempted** (part change). Band room y 47-60 (`band_room.py`, `screens/band-*.json`):

  | board | SW_B crosses on | SW_B via-legal cells | LOW crosses on | SELV |
  |---|---|---|---|---|
  | s32 | In2 | 1 | F, B | nowhere |
  | build 1 | In2, In3, In4 | 1 | also In3 | nowhere |
  | b2 | In2, In4 | 0 | F, B | nowhere |

  On b2 the In3 bus_p image takes In3 back. HS-B can still cross on In4 without a via in the band, but 30a needs its
  vias outside it.
- **Not adopted on the branch:** the tracked board outputs are still stage 32. Adopting s33 means three things: make
  `stackup-6L.json` the stack (or point `build_native21` at it), put `copper-s33.json` in `layout/copper.json`, and
  update the FAB-NOTE to the 6-layer build. Re-run with:

  ```
  NATIVE21_STACKUP=$U/native-21/stackup-6L.json SHEET_BARREL=stackup sh passes33.sh base-s32.json OUT FIRST_DRC FIRST_FILLS
  ```

  then `chain.sh native21s33 OUT/j1 BUILD`, with `F8_Z=stackup` for `run_ocp.py`.
